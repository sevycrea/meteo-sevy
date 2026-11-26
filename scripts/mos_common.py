#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prévision corrigée par la station (MOS : Model Output Statistics).

Principe : les modèles numériques (ICON, MeteoSwiss ICON-CH2, MetNo, ECMWF)
voient arriver le temps ; la station IVINEL2 apprend leurs erreurs propres à
Vinelz (lac, brouillard, nuits froides) et les corrige pour J0, J+1 et J+2.
Au-delà de J+2, le modèle numérique est affiché sans correction.

Module commun à train_mos.py (entraînement nocturne) et predict_mos.py
(prévision). Aucune dépendance au-delà de numpy et de la bibliothèque
standard ; les modèles sont stockés en JSON (pas de pickle).
"""

import json
import math
import os
import sys
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from http_helpers import get_json_with_retry  # noqa: E402

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_FILE = os.path.join(BASE_DIR, "data", "models", "mos_model.json")
NWP_CACHE_DIR = os.path.join(BASE_DIR, "data", "mos")
ARCHIVE_DIR = os.path.join(BASE_DIR, "data", "archive")

LAT = 47.03
LON = 7.08
TZ_NAME = "Europe/Zurich"
TZ = ZoneInfo(TZ_NAME)

# Modèles numériques utilisés (Open-Meteo). Le premier est la base affichée.
MODELS = ["icon_seamless", "meteoswiss_icon_ch2", "metno_seamless", "ecmwf_ifs025"]
PRIMARY = MODELS[0]

# Jours de calcul : jours UTC (comme les jours de meteo_data.json, agrégés
# par le collecteur en UTC), identiques à l'entraînement et à la prévision.
# L'affichage horaire reste en heure suisse.
#
# Échéance k = (jour cible UTC − jour UTC courant) : 0, 1 ou 2
#   -> prévision archivée utilisée pour l'apprentissage : previous_day{k}
#      (k = 0 : dernière sortie disponible pour chaque heure)
#   -> dernier jour complet de la station connu au moment de la prévision : D − (k+1)
NWP_LEAD = {0: 0, 1: 1, 2: 2}
HORIZONS = [0, 1, 2]
CACHE_VERSION = 2   # v2 : jours UTC, échéances 0/1/2

# Correction maximale tolérée par rapport au modèle brut (garde-fou contre une
# donnée aberrante ; le test hors échantillon donne des corrections < 3 °C).
MAX_CORRECTION = 4.0

RAIN_THRESHOLD_MM = 0.5

STATION_DAILY_URL = "https://data.sevy-creations.net/meteo_data.json"
STATION_HOURLY_URL = "https://data.sevy-creations.net/meteo_data_hourly.json"

PREVIOUS_RUNS_URL = "https://previous-runs-api.open-meteo.com/v1/forecast"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

# Variables de la station : uniquement minima, maxima et pluie.
# Les moyennes de meteo_data.json (temp_avg, hum_avg, pressure_avg…) sont
# faussées depuis juin 2026 : le collecteur lit une fenêtre WU glissante de 24 h
# et recalcule la moyenne de la veille sur ses dernières heures (mesuré :
# temp_avg inférieure de 1,5 °C à la moyenne horaire sur 89 jours). Les min/max
# sont protégés à la fusion, donc fiables. On utilise le milieu (min+max)/2.
FEATURE_NAMES = (
    [f"{m}_{v}" for m in MODELS for v in ("tavg", "tmin", "tmax", "log_precip")]
    + ["st_tmid", "st_tmax", "st_tmin", "st_pressure_mid", "st_hum_mid",
       "st_tmid_prev", "st_pressure_mid_prev", "err_primary_last",
       "season_sin", "season_cos"]
)
# Cibles apprises : minimum et maximum. La moyenne affichée = moyenne ICON
# décalée de la moyenne des deux corrections.
TEMP_TARGETS = {"tmax": "temp_max", "tmin": "temp_min"}


def today_local():
    return datetime.now(TZ).date()


def today_utc():
    return datetime.now(timezone.utc).date()


def utc_to_local(t):
    """'AAAA-MM-JJTHH:MM' en UTC -> datetime en heure suisse."""
    return datetime.fromisoformat(t).replace(tzinfo=timezone.utc).astimezone(TZ)


def iso(d):
    return d.isoformat()


def parse_date(s):
    return date.fromisoformat(s)


# ============================================
# TÉLÉCHARGEMENTS
# ============================================

def fetch_station_daily(log=print):
    bust = int(datetime.now().timestamp())
    data = get_json_with_retry(f"{STATION_DAILY_URL}?t={bust}", timeout=30, attempts=3, log=log)
    if not isinstance(data, dict) or not data:
        return None
    return data


def fetch_station_hourly(log=print):
    bust = int(datetime.now().timestamp())
    data = get_json_with_retry(f"{STATION_HOURLY_URL}?t={bust}", timeout=30, attempts=3, log=log)
    if not isinstance(data, dict) or not data:
        return None
    return data


def _url(base, params):
    return base + "?" + urllib.parse.urlencode(params, safe=",")


def daily_from_hourly(times, temps, precs, local=False):
    """Agrège des séries horaires (horodatage UTC) en valeurs journalières :
    jours UTC par défaut, jours suisses si local=True (affichage).

    Un jour n'est retenu que s'il a au moins 20 heures de température."""
    buckets = {}
    for i, t in enumerate(times):
        d = utc_to_local(t).date().isoformat() if local else t[:10]
        b = buckets.setdefault(d, {"t": [], "p": []})
        tv = temps[i] if temps is not None and i < len(temps) else None
        pv = precs[i] if precs is not None and i < len(precs) else None
        if tv is not None:
            b["t"].append(float(tv))
        if pv is not None:
            b["p"].append(float(pv))
    out = {}
    for d, b in buckets.items():
        if len(b["t"]) < 20:
            continue
        out[d] = {
            "tavg": round(sum(b["t"]) / len(b["t"]), 3),
            "tmin": round(min(b["t"]), 2),
            "tmax": round(max(b["t"]), 2),
            "precip": round(sum(b["p"]), 2) if len(b["p"]) >= 20 else None,
        }
    return out


def fetch_previous_runs(model, start, end, log=print):
    """Prévisions archivées (jours UTC) : pour chaque jour D, la dernière
    sortie (lead 0), celle de 24 h avant (lead 1) et de 48 h avant (lead 2).
    Retourne {0: {date: agg}, 1: {...}, 2: {...}}."""
    params = {
        "latitude": LAT, "longitude": LON, "timezone": "GMT", "models": model,
        "start_date": iso(start), "end_date": iso(end),
        "hourly": ",".join([
            "temperature_2m", "temperature_2m_previous_day1", "temperature_2m_previous_day2",
            "precipitation", "precipitation_previous_day1", "precipitation_previous_day2",
        ]),
    }
    raw = get_json_with_retry(_url(PREVIOUS_RUNS_URL, params), timeout=60, attempts=4, log=log)
    if not raw or "hourly" not in raw:
        log(f"⚠️  Archive {model} indisponible")
        return None
    h = raw["hourly"]
    times = h.get("time", [])
    res = {}
    for lead in (0, 1, 2):
        sfx = "" if lead == 0 else f"_previous_day{lead}"
        res[lead] = daily_from_hourly(times, h.get(f"temperature_2m{sfx}"), h.get(f"precipitation{sfx}"))
    return res


def fetch_forecast(model, extra_hourly=False, log=print):
    """Prévision actuelle sur 8 jours (horodatage UTC)."""
    hourly = ["temperature_2m", "precipitation"]
    if extra_hourly:
        hourly += ["cloud_cover", "wind_speed_10m", "pressure_msl"]
    params = {
        "latitude": LAT, "longitude": LON, "timezone": "GMT", "models": model,
        "forecast_days": 8, "past_days": 1, "hourly": ",".join(hourly),
    }
    raw = get_json_with_retry(_url(FORECAST_URL, params), timeout=30, attempts=4, log=log)
    if not raw or "hourly" not in raw:
        log(f"⚠️  Prévision {model} indisponible")
        return None
    return raw


def fetch_rain_probability(log=print):
    """Probabilité de précipitations journalière (ensembles Open-Meteo, best_match)."""
    params = {
        "latitude": LAT, "longitude": LON, "timezone": TZ_NAME, "models": "best_match",
        "forecast_days": 8, "daily": "precipitation_probability_max",
    }
    raw = get_json_with_retry(_url(FORECAST_URL, params), timeout=30, attempts=3, log=log)
    try:
        d = raw["daily"]
        return {t: p for t, p in zip(d["time"], d["precipitation_probability_max"]) if p is not None}
    except Exception:
        return {}


# ============================================
# CACHE DES PRÉVISIONS ARCHIVÉES (dans le dépôt)
# ============================================

def cache_path(model):
    return os.path.join(NWP_CACHE_DIR, f"nwp_archive_{model}.json")


def load_cache(model):
    empty = {"version": CACHE_VERSION, "0": {}, "1": {}, "2": {}}
    try:
        with open(cache_path(model), "r", encoding="utf-8") as f:
            c = json.load(f)
        if c.get("version") != CACHE_VERSION:
            return empty
        return {"version": CACHE_VERSION, "0": c.get("0", {}), "1": c.get("1", {}), "2": c.get("2", {})}
    except Exception:
        return empty


def update_cache(model, first_day, yesterday, log=print):
    """Complète le cache : téléchargement complet s'il est vide, sinon les
    10 derniers jours (les valeurs déjà présentes sont rafraîchies)."""
    cache = load_cache(model)
    known = sorted(cache["0"].keys())
    start = first_day if not known else max(first_day, parse_date(known[-1]) - timedelta(days=10))
    if start > yesterday:
        return cache
    res = fetch_previous_runs(model, start, yesterday, log=log)
    if res:
        for lead in (0, 1, 2):
            cache[str(lead)].update(res[lead])
        log(f"   {model} : {len(cache['0'])} jours en cache (ajout {iso(start)} → {iso(yesterday)})")
    return cache


# ============================================
# VARIABLES EXPLICATIVES
# ============================================

def _st(station, d, key):
    day = station.get(iso(d))
    if not isinstance(day, dict):
        return None
    v = day.get(key)
    return float(v) if isinstance(v, (int, float)) else None


def _mid(station, d, base):
    lo, hi = _st(station, d, f"{base}_min"), _st(station, d, f"{base}_max")
    return None if lo is None or hi is None else (lo + hi) / 2


def build_features(nwp_day_by_model, station, primary_lead1, target, k):
    """Vecteur explicatif pour le jour `target` à l'échéance k.

    nwp_day_by_model : {model: {"tavg","tmin","tmax","precip"}} pour `target`
    station          : meteo_data.json (jours complets uniquement)
    primary_lead1    : {date: agg} prévision à 24 h du modèle principal
                       (sert à mesurer son erreur la plus récente)
    Retourne None si une donnée indispensable manque.
    """
    prim = nwp_day_by_model.get(PRIMARY)
    if not prim:
        return None
    f = []
    for m in MODELS:
        v = nwp_day_by_model.get(m) or prim
        p = v.get("precip")
        if p is None:
            p = prim.get("precip") or 0.0
        f += [v["tavg"], v["tmin"], v["tmax"], math.log1p(max(p, 0.0))]

    last = target - timedelta(days=k + 1)
    prev = last - timedelta(days=1)
    vals = [_mid(station, last, "temp"), _st(station, last, "temp_max"),
            _st(station, last, "temp_min"), _mid(station, last, "pressure"),
            _mid(station, last, "hum"), _mid(station, prev, "temp"),
            _mid(station, prev, "pressure")]
    if any(v is None for v in vals):
        return None
    f += vals

    # Dernière erreur connue du modèle principal (milieu min/max, prévision à 24 h)
    p_last = primary_lead1.get(iso(last))
    f.append((p_last["tmin"] + p_last["tmax"]) / 2 - vals[0] if p_last else 0.0)

    doy = target.timetuple().tm_yday
    f += [math.sin(2 * math.pi * doy / 365.25), math.cos(2 * math.pi * doy / 365.25)]
    return f


# ============================================
# MODÈLES (numpy pur, sérialisables en JSON)
# ============================================

def _standardize_fit(X):
    mu = X.mean(axis=0)
    sd = X.std(axis=0)
    sd[sd < 1e-9] = 1.0
    return mu, sd


def fit_ridge(X, y, alpha):
    mu, sd = _standardize_fit(X)
    Z = (X - mu) / sd
    ym = float(y.mean())
    A = Z.T @ Z + alpha * np.eye(Z.shape[1])
    w = np.linalg.solve(A, Z.T @ (y - ym))
    return {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist(), "b": ym, "alpha": alpha}


def predict_linear(m, X):
    X = np.atleast_2d(np.asarray(X, dtype=float))
    return ((X - np.array(m["mu"])) / np.array(m["sd"])) @ np.array(m["w"]) + m["b"]


def fit_logistic(X, y, alpha, iters=50):
    """Régression logistique L2 par Newton (IRLS)."""
    mu, sd = _standardize_fit(X)
    Z = np.hstack([np.ones((len(X), 1)), (X - mu) / sd])
    w = np.zeros(Z.shape[1])
    reg = alpha * np.eye(Z.shape[1])
    reg[0, 0] = 0.0
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-np.clip(Z @ w, -30, 30)))
        g = Z.T @ (p - y) + reg @ w
        H = (Z * (p * (1 - p))[:, None]).T @ Z + reg + 1e-9 * np.eye(Z.shape[1])
        step = np.linalg.solve(H, g)
        w -= step
        if np.max(np.abs(step)) < 1e-7:
            break
    return {"mu": mu.tolist(), "sd": sd.tolist(), "w": w[1:].tolist(), "b": float(w[0]), "alpha": alpha}


def predict_proba(m, X):
    z = predict_linear(m, X)
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def load_model(log=print):
    try:
        with open(MODEL_FILE, "r", encoding="utf-8") as f:
            m = json.load(f)
        if m.get("feature_names") != FEATURE_NAMES:
            log("⚠️  mos_model.json : variables différentes de la version du code — ignoré")
            return None
        return m
    except Exception as e:
        log(f"⚠️  mos_model.json illisible : {e}")
        return None
