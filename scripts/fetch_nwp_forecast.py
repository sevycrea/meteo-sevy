#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Récupération prévision NWP (Numerical Weather Prediction) via Open-Meteo
Modèle : MetNo Seamless (MeteoSwiss ICON + ECMWF)
Coordonnées : Vinelz 47.03°N, 7.08°E

Sauvegarde :
  - data/json/nwp_forecast.json : prévision actuelle (7 jours)
  - data/json/nwp_history.json  : historique des prévisions (pour futur MOS)

Utilisé par predict_hourly.py et predict_weather_multihorizon.py.
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftp_helpers import upload_data
from http_helpers import get_json_with_retry
from io_helpers import atomic_write_json

# ============================================
# CONFIGURATION (chemins relatifs au repo)
# ============================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "data", "json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "nwp_forecast.log")

NWP_FILE      = os.path.join(DATA_DIR, "nwp_forecast.json")
NWP_HIST_FILE = os.path.join(DATA_DIR, "nwp_history.json")

LAT = 47.03
LON = 7.08

# Variables journalières à récupérer
DAILY_VARS = [
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
]

# Variables horaires (incluant signaux d'orage : weathercode WMO + CAPE)
HOURLY_VARS = [
    "temperature_2m",
    "precipitation",
    "pressure_msl",
    "cloud_cover",
    "wind_speed_10m",
    "wind_gusts_10m",        # rafales (utile pour détection vent fort à venir)
    "weathercode",           # codes WMO : 95-99 = orages
    "cape",                  # Convective Available Potential Energy (J/kg)
]

# FTP via variables d'environnement (GitHub Actions secrets)
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")

# Repli si Open-Meteo est indisponible (429/502/timeout) : on réutilise le DERNIER
# NWP publié (servi par data.sevy-creations.net, donc dispo même quand Open-Meteo
# est down), À CONDITION qu'il ne soit pas trop vieux. Objectif : ne plus figer
# l'écran de prévisions sur un simple hoquet passager. Au-delà du plafond, on
# échoue franchement (exit 1) comme avant — pas de NWP ancien servi en douce.
FALLBACK_URL       = "https://data.sevy-creations.net/nwp_forecast.json"
MAX_FALLBACK_HOURS = 12   # NWP de repli accepté jusqu'à 12 h (cadence normale = 4×/j)

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ============================================
# LOGGING
# ============================================

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + "\n")

# ============================================
# FETCH
# ============================================

def fetch_nwp():
    """Récupère la prévision NWP via Open-Meteo avec retry.

    4 tentatives avec backoff pour absorber les coupures réseau ou le
    rate-limiting (429/502) d'Open-Meteo. Si tout échoue → None (le main
    tentera alors le repli sur le dernier NWP connu).
    """
    daily_params = ",".join(DAILY_VARS)
    hourly_params = ",".join(HOURLY_VARS)
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={LAT}&longitude={LON}"
        f"&daily={daily_params}"
        f"&hourly={hourly_params}"
        f"&timezone=Europe/Zurich"
        f"&forecast_days=8"
        f"&models=metno_seamless"
    )

    raw = get_json_with_retry(url, timeout=30, attempts=4, log=log)
    if raw is None:
        log("❌ Open-Meteo inaccessible après 4 tentatives")
        return None
    log(f"✅ NWP téléchargé ({raw.get('generationtime_ms', 0):.1f} ms)")
    return raw

def load_fallback():
    """Repli : récupère le dernier nwp_forecast.json publié (data.sevy-creations.net)
    et renvoie (contenu, âge_en_heures). Sert quand Open-Meteo est momentanément
    indisponible — ce fichier est servi par l'hébergeur, pas par Open-Meteo."""
    bust = int(datetime.now().timestamp())
    data = get_json_with_retry(f"{FALLBACK_URL}?t={bust}", timeout=20, attempts=2, log=log)
    if not data:
        return None, None
    try:
        age_h = (datetime.now() - datetime.fromisoformat(data["fetched_at"])).total_seconds() / 3600
    except Exception:
        return None, None
    return data, age_h

# ============================================
# TRAITEMENT
# ============================================

def aggregate_hourly_periods(hourly, date_str):
    """
    Agrège les données horaires en 3 périodes :
      p1 = matin    04h-12h
      p2 = après-midi 12h-20h
      p3 = nuit     20h-04h (lendemain)
    """
    times = hourly.get('time', [])
    temps = hourly.get('temperature_2m', [])
    precip = hourly.get('precipitation', [])
    pressure = hourly.get('pressure_msl', [])
    cloud = hourly.get('cloud_cover', [])
    wind = hourly.get('wind_speed_10m', [])

    def hours_for(date, h_start, h_end):
        prefix = f"{date}T"
        return [i for i, t in enumerate(times) if t.startswith(prefix)
                and h_start <= int(t[11:13]) < h_end]

    def safe_mean(lst, idxs):
        vals = [lst[i] for i in idxs if i < len(lst) and lst[i] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def safe_sum(lst, idxs):
        vals = [lst[i] for i in idxs if i < len(lst) and lst[i] is not None]
        return round(sum(vals), 1) if vals else 0.0

    result = {}
    for period, h_start, h_end in [('p1', 4, 12), ('p2', 12, 20), ('p3', 20, 24)]:
        idxs = hours_for(date_str, h_start, h_end)
        result[period] = {
            'temp_avg':     safe_mean(temps, idxs),
            'precip_sum':   safe_sum(precip, idxs),
            'pressure_avg': safe_mean(pressure, idxs),
            'cloud_avg':    safe_mean(cloud, idxs),
            'wind_avg':     safe_mean(wind, idxs),
        }
    return result

def extract_hourly_for_date(hourly, date_str):
    """Extrait les données heure par heure pour une date donnée."""
    times    = hourly.get('time', [])
    temps    = hourly.get('temperature_2m', [])
    precip   = hourly.get('precipitation', [])
    pressure = hourly.get('pressure_msl', [])
    cloud    = hourly.get('cloud_cover', [])
    wind     = hourly.get('wind_speed_10m', [])
    gusts    = hourly.get('wind_gusts_10m', [])
    wmo      = hourly.get('weathercode', [])
    cape     = hourly.get('cape', [])

    prefix = f"{date_str}T"
    hours = []
    for i, t in enumerate(times):
        if not t.startswith(prefix):
            continue
        h = int(t[11:13])
        hours.append({
            'hour':          h,
            'temperature':   temps[i]    if i < len(temps)    else None,
            'precipitation': precip[i]   if i < len(precip)   else 0.0,
            'pressure':      pressure[i] if i < len(pressure) else None,
            'cloud_cover':   cloud[i]    if i < len(cloud)    else None,
            'wind_speed':    wind[i]     if i < len(wind)     else None,
            'wind_gust':     gusts[i]    if i < len(gusts)    else None,
            'weathercode':   wmo[i]      if i < len(wmo)      else None,
            'cape':          cape[i]     if i < len(cape)     else None,
        })
    return hours

def parse_nwp(raw):
    daily = raw.get('daily', {})
    hourly = raw.get('hourly', {})
    dates = daily.get('time', [])

    forecasts = {}
    for i, date in enumerate(dates):
        def get(key, fallback=None):
            vals = daily.get(key, [])
            return vals[i] if i < len(vals) else fallback

        temp_max = get('temperature_2m_max')
        temp_min = get('temperature_2m_min')
        temp_avg = round((temp_max + temp_min) / 2, 1) if temp_max and temp_min else None

        forecasts[date] = {
            'temp_max':     temp_max,
            'temp_min':     temp_min,
            'temp_avg':     temp_avg,
            'precip_sum':   get('precipitation_sum', 0.0),
            'rain_prob':    get('precipitation_probability_max', 0),
            'wind_max':     get('wind_speed_10m_max'),
            'gust_max':     get('wind_gusts_10m_max'),
            'periods':      aggregate_hourly_periods(hourly, date),
            'hourly':       extract_hourly_for_date(hourly, date),
        }
    return forecasts

# ============================================
# SAUVEGARDE
# ============================================

def save_nwp(forecasts):
    output = {
        'fetched_at': datetime.now().isoformat(),
        'source':     'open-meteo / metno_seamless',
        'latitude':   LAT,
        'longitude':  LON,
        'forecasts':  forecasts,
    }
    atomic_write_json(NWP_FILE, output)
    log(f"✅ nwp_forecast.json sauvegardé ({len(forecasts)} jours)")

def update_history(forecasts):
    today = datetime.now().strftime('%Y-%m-%d')
    history = {}
    if os.path.exists(NWP_HIST_FILE):
        try:
            with open(NWP_HIST_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            history = {}

    history[today] = forecasts

    # Garder 90 jours max
    if len(history) > 90:
        oldest = sorted(history.keys())[:-90]
        for k in oldest:
            del history[k]

    atomic_write_json(NWP_HIST_FILE, history)
    log(f"✅ nwp_history.json mis à jour ({len(history)} entrées)")

# ============================================
# UPLOAD FTP
# ============================================

def upload_nwp():
    if not (FTP_HOST and FTP_USER and FTP_PASS):
        log("⚠️  FTP non configuré (env vars manquants) — upload ignoré")
        return
    try:
        import ftplib
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        with open(NWP_FILE, 'rb') as f:
            ftp.storbinary('STOR nwp_forecast.json', f)
        ftp.quit()
        log("✅ nwp_forecast.json uploadé sur le serveur")

        # Double upload vers data.sevy-creations.net (best-effort)
        upload_data(NWP_FILE, 'nwp_forecast.json', log=log)
    except Exception as e:
        log(f"⚠️  Upload FTP échoué : {e}")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 60)
    log("🌐 RÉCUPÉRATION PRÉVISION NWP — Open-Meteo / MetNo")
    log("=" * 60)

    raw = fetch_nwp()
    if not raw:
        # Open-Meteo indisponible. Plutôt que de tout faire échouer (et figer
        # l'écran de prévisions), on tente un REPLI sur le dernier NWP connu —
        # uniquement s'il est encore assez frais (≤ MAX_FALLBACK_HOURS).
        log("⚠️  Open-Meteo indisponible — tentative de repli sur le dernier NWP connu…")
        fb, age_h = load_fallback()
        if fb and age_h is not None and age_h <= MAX_FALLBACK_HOURS:
            # On réécrit le dernier bon NWP sur le disque pour que les étapes ML
            # (predict_weather_multihorizon, predict_hourly) tournent dessus.
            atomic_write_json(NWP_FILE, fb)
            log(f"✅ Repli accepté : NWP daté de {age_h:.1f} h (≤ {MAX_FALLBACK_HOURS} h).")
            log("ℹ️  Workflow vert : prévisions régénérées sur ce NWP encore valable "
                "(évite l'écran figé). Le NWP frais reviendra au prochain run.")
            return  # exit 0 → les étapes suivantes s'exécutent
        # Pas de repli exploitable (introuvable ou trop vieux) → échec franc, comme avant.
        log(f"❌ Aucun repli exploitable (NWP introuvable ou > {MAX_FALLBACK_HOURS} h) "
            "— abandon (exit 1)")
        sys.exit(1)

    forecasts = parse_nwp(raw)

    log("")
    log("📅 Prévisions NWP pour les 7 prochains jours :")
    for date, fc in forecasts.items():
        rain_bar = '🌧️ ' if fc['rain_prob'] > 50 else ('🌦️ ' if fc['rain_prob'] > 20 else '☀️ ')
        log(f"   {date} : {fc['temp_min']}–{fc['temp_max']}°C  "
            f"pluie {fc['rain_prob']}%  {rain_bar}  précip {fc['precip_sum']}mm")

    save_nwp(forecasts)
    update_history(forecasts)
    upload_nwp()

    log("")
    log("✅ Terminé")
    log("=" * 60)

if __name__ == "__main__":
    main()
