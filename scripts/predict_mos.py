#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prévision corrigée par la station IVINEL2 (MOS) — remplace
predict_weather_multihorizon.py + predict_hourly.py.

- J0, J+1, J+2 : modèles numériques (ICON, ICON-CH2, MetNo, ECMWF) corrigés
  par ce que la station a appris (data/models/mos_model.json).
- J+3 à J+6   : ICON sans correction (marqué « indicatif »).
- Si le modèle appris manque ou si une donnée station manque : ICON brut,
  signalé dans le fichier (jamais de correction inventée).

Sorties (même format qu'avant, lu par le site et par les alertes) :
  data/predictions.json             — 3 jours, format multihorizon
  data/json/predictions_hourly.json — 7 jours, créneaux de 2 h
  data/mos/verification.json        — prévisions émises puis erreurs mesurées
"""

import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mos_common as mc  # noqa: E402
from ftp_helpers import upload_data, upload_legacy  # noqa: E402
from io_helpers import atomic_write_json  # noqa: E402

PRED_FILE = os.path.join(mc.BASE_DIR, "data", "predictions.json")
HOURLY_FILE = os.path.join(mc.BASE_DIR, "data", "json", "predictions_hourly.json")
VERIF_FILE = os.path.join(mc.NWP_CACHE_DIR, "verification.json")
LOG_FILE = os.path.join(mc.BASE_DIR, "logs", "predictions_mos.log")
SLOT_SIZE = 2
DAY_LABELS = ["Aujourd'hui", "Demain", "Après-demain", "J+3", "J+4", "J+5", "J+6"]
DAY_NAMES_EN = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(HOURLY_FILE), exist_ok=True)
os.makedirs(mc.NWP_CACHE_DIR, exist_ok=True)


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================
# DONNÉES DU MODÈLE PRINCIPAL
# ============================================

def hourly_by_date(raw):
    """Heures regroupées par jour SUISSE (affichage) :
    {date: [ {hour, temperature, precipitation, cloud_cover, wind_speed, pressure} ]}"""
    h = raw["hourly"]
    out = {}
    for i, t in enumerate(h["time"]):
        def g(key):
            v = h.get(key)
            return v[i] if v is not None and i < len(v) else None
        loc = mc.utc_to_local(t)
        out.setdefault(loc.date().isoformat(), []).append({
            "hour": loc.hour,
            "temperature": g("temperature_2m"),
            "precipitation": g("precipitation"),
            "cloud_cover": g("cloud_cover"),
            "wind_speed": g("wind_speed_10m"),
            "pressure": g("pressure_msl"),
        })
    return out


def adjust_hours(hours, raw_day, cmin, cmax):
    """Déforme la courbe horaire pour que son minimum devienne cmin et son
    maximum cmax (décalage interpolé selon la position de chaque heure entre
    le min et le max bruts)."""
    rmin, rmax = raw_day["tmin"], raw_day["tmax"]
    dmin, dmax = cmin - rmin, cmax - rmax
    span = rmax - rmin
    out = []
    for h in hours:
        t = h["temperature"]
        if t is None:
            out.append(dict(h))
            continue
        frac = 0.5 if span < 0.1 else min(max((t - rmin) / span, 0.0), 1.0)
        out.append({**h, "temperature": t + dmin + frac * (dmax - dmin)})
    return out


# ============================================
# CRÉNEAUX ET PÉRIODES (format attendu par le site)
# ============================================

def build_slots(hours, day_rain_prob):
    by_hour = {h["hour"]: h for h in hours}
    slots = []
    for start in range(0, 24, SLOT_SIZE):
        sel = [by_hour[x] for x in range(start, start + SLOT_SIZE) if x in by_hour]
        if not sel:
            continue
        def avg(key, nd=1):
            v = [s[key] for s in sel if s[key] is not None]
            return round(sum(v) / len(v), nd) if v else None
        precs = [s["precipitation"] for s in sel if s["precipitation"] is not None]
        precip = round(sum(precs), 1) if precs else 0.0
        cloud = avg("cloud_cover", 0)
        cloud = int(cloud) if cloud is not None else None
        if precip > 2.0:
            rain_prob, icon = min(100, int(day_rain_prob * 1.1)), "🌧️"
        elif precip > 0.5:
            rain_prob, icon = int(day_rain_prob * 0.8), "🌦️"
        elif precip > 0.0:
            rain_prob, icon = int(day_rain_prob * 0.5), ("🌦️" if precip > 0.1 else None)
        else:
            rain_prob, icon = max(0, int(day_rain_prob * 0.15)), None
        if icon is None:
            icon = "☁️" if cloud is not None and cloud > 75 else ("⛅" if cloud is not None and cloud > 40 else "☀️")
        slots.append({
            "time_start": f"{start:02d}:00", "time_end": f"{start + SLOT_SIZE:02d}:00",
            "label": f"{start:02d}h–{start + SLOT_SIZE:02d}h", "icon": icon,
            "temperature": avg("temperature"), "precipitation": precip, "rain_prob": rain_prob,
            "cloud_cover": cloud, "wind_speed": avg("wind_speed"), "pressure": avg("pressure"),
        })
    return slots


def build_periods(slots):
    order = ["🌧️", "🌦️", "☁️", "⛅", "☀️"]

    def agg(starts):
        sel = [s for s in slots if int(s["time_start"][:2]) in starts]
        temps = [s["temperature"] for s in sel if s["temperature"] is not None]
        if not temps:
            return {}
        rp = max([s["rain_prob"] for s in sel] or [0])
        icons = [s["icon"] for s in sel]
        return {
            "temp": round(sum(temps) / len(temps), 1), "rain_prob": rp,
            "rain_risk": "élevé" if rp >= 60 else ("modéré" if rp >= 30 else "faible"),
            "icon": next((i for i in order if i in icons), "☀️"),
        }
    return {
        "matin": {"name": "Matin (06h–12h)", **agg([6, 8, 10])},
        "apres_midi": {"name": "Après-midi (12h–20h)", **agg([12, 14, 16, 18])},
        "nuit": {"name": "Nuit (20h–06h)", **agg([20, 22, 0, 2, 4])},
    }


# ============================================
# PRÉVISION
# ============================================

def correct_day(model, k, target, nwp_today, station, prim_lead1):
    """Retourne (tavg, tmin, tmax, rain_prob|None, appliqué: bool, raison)."""
    raw = nwp_today[mc.PRIMARY]
    if model is None:
        return raw["tavg"], raw["tmin"], raw["tmax"], None, False, "modèle appris absent"
    f = mc.build_features(nwp_today, station, prim_lead1, target, k)
    if f is None:
        return raw["tavg"], raw["tmin"], raw["tmax"], None, False, "mesure station manquante"
    hz = model["horizons"][str(k)]
    vals = {}
    for name in ("tmin", "tmax"):
        m = hz["temp"][name]
        if m.get("use"):
            v = float(mc.predict_linear(m, f)[0])
            vals[name] = float(np.clip(v, raw[name] - mc.MAX_CORRECTION, raw[name] + mc.MAX_CORRECTION))
        else:
            vals[name] = raw[name]
    tmin, tmax = min(vals["tmin"], vals["tmax"]), max(vals["tmin"], vals["tmax"])
    # Moyenne : moyenne ICON décalée de la moyenne des deux corrections
    tavg = raw["tavg"] + ((tmin - raw["tmin"]) + (tmax - raw["tmax"])) / 2
    tavg = min(max(tavg, tmin), tmax)
    rain = None
    if hz["rain"].get("use"):
        rain = float(mc.predict_proba(hz["rain"], f)[0]) * 100
    return tavg, tmin, tmax, rain, True, "corrigé par la station"


def update_verification(issued, station, today):
    """Garde la première prévision émise chaque jour, puis calcule l'erreur
    réelle dès que la station a mesuré la journée."""
    try:
        with open(VERIF_FILE, "r", encoding="utf-8") as f:
            v = json.load(f)
        if not isinstance(v.get("issued"), dict):
            raise ValueError("format inattendu")
    except Exception:
        v = {"issued": {}}
    key = mc.iso(today)
    if key not in v["issued"]:
        v["issued"][key] = issued
    # Tronquer à 400 jours d'émission
    for old in sorted(v["issued"])[:-400]:
        del v["issued"][old]
    stats = {}
    for issue, fcs in v["issued"].items():
        for fc in fcs:
            obs = station.get(fc["date"])
            if (fc["date"] >= key or not isinstance(obs, dict) or obs.get("temp_min") is None
                    or obs.get("temp_max") is None or "raw_tmin" not in fc):
                continue
            s = stats.setdefault(str(fc["k"]), {"n": 0, "abs_corrected": 0.0, "abs_raw": 0.0, "rain_ok": 0})
            s["n"] += 1
            # Erreur moyenne sur le minimum et le maximum (champs fiables de la station)
            s["abs_corrected"] += (abs(fc["tmin"] - obs["temp_min"]) + abs(fc["tmax"] - obs["temp_max"])) / 2
            s["abs_raw"] += (abs(fc["raw_tmin"] - obs["temp_min"]) + abs(fc["raw_tmax"] - obs["temp_max"])) / 2
            rained = (obs.get("rain") or 0) > mc.RAIN_THRESHOLD_MM
            s["rain_ok"] += int((fc["rain_prob"] >= 50) == rained)
    v["summary"] = {
        k: {"n_days": s["n"], "mae_minmax_corrected": round(s["abs_corrected"] / s["n"], 2),
            "mae_minmax_raw_icon": round(s["abs_raw"] / s["n"], 2),
            "rain_accuracy": round(s["rain_ok"] / s["n"], 3)}
        for k, s in sorted(stats.items()) if s["n"]
    }
    v["updated_at"] = datetime.now(mc.TZ).isoformat(timespec="seconds")
    atomic_write_json(VERIF_FILE, v)
    return v["summary"]


def main():
    log("=" * 60)
    log("🔮 PRÉVISION CORRIGÉE PAR LA STATION IVINEL2")
    log("=" * 60)
    today = mc.today_local()     # jours affichés (heure suisse)
    utc_today = mc.today_utc()   # jours de calcul (UTC, comme la station)
    model = mc.load_model(log=log)
    if model:
        log(f"✅ Modèle appris du {model['trained_at']}")
    else:
        log("⚠️  Pas de modèle appris : ICON brut affiché")

    station = mc.fetch_station_daily(log=log)
    if not station:
        log("⚠️  meteo_data.json en ligne indisponible — archive du dépôt")
        try:
            with open(os.path.join(mc.ARCHIVE_DIR, "station_daily.json"), "r", encoding="utf-8") as f:
                station = json.load(f)
        except Exception:
            station = {}
    station = {d: v for d, v in station.items() if d < mc.iso(utc_today) and isinstance(v, dict)}
    log(f"📡 Station : {len(station)} jours complets, dernier {max(station) if station else '—'}")

    forecasts = {}
    for i, m in enumerate(mc.MODELS):
        raw = mc.fetch_forecast(m, extra_hourly=(i == 0), log=log)
        if raw:
            forecasts[m] = raw
    if mc.PRIMARY not in forecasts:
        log("❌ Prévision ICON indisponible — abandon (les fichiers précédents restent en ligne)")
        sys.exit(1)
    daily_utc = {m: mc.daily_from_hourly(r["hourly"]["time"], r["hourly"]["temperature_2m"],
                                         r["hourly"]["precipitation"]) for m, r in forecasts.items()}
    p = forecasts[mc.PRIMARY]["hourly"]
    daily_loc = mc.daily_from_hourly(p["time"], p["temperature_2m"], p["precipitation"], local=True)
    hours_primary = hourly_by_date(forecasts[mc.PRIMARY])

    # Erreur récente d'ICON (prévision à 24 h des derniers jours)
    prim_lead1 = dict(mc.load_cache(mc.PRIMARY)["1"])
    recent = mc.fetch_previous_runs(mc.PRIMARY, utc_today - timedelta(days=6), utc_today - timedelta(days=1), log=log)
    if recent:
        prim_lead1.update(recent[1])

    ens_prob = mc.fetch_rain_probability(log=log)
    metrics = (model or {}).get("horizons", {})

    days_hourly, days_ml, issued = [], [], []
    for k in range(7):
        target = today + timedelta(days=k)
        ds = mc.iso(target)
        raw_loc = daily_loc.get(ds)
        if not raw_loc or ds not in hours_primary:
            log(f"⚠️  {ds} : pas de prévision ICON complète — jour ignoré")
            continue
        # Échéance de calcul : écart au jour UTC courant (vers minuit en été,
        # le jour suisse a déjà changé alors que le jour UTC non : on prend alors
        # l'échéance suivante, dont le dernier jour station est bien complet).
        h = (target - utc_today).days
        raw_utc = daily_utc[mc.PRIMARY].get(ds)
        applied, reason, rain = False, "au-delà de J+2 : ICON brut", None
        d_avg = d_min = d_max = 0.0
        if h in mc.HORIZONS and raw_utc:
            nwp_day = {m: daily_utc[m].get(ds) for m in daily_utc}
            c_avg, c_min, c_max, rain, applied, reason = correct_day(model, h, target, nwp_day, station, prim_lead1)
            if applied:
                d_avg, d_min, d_max = c_avg - raw_utc["tavg"], c_min - raw_utc["tmin"], c_max - raw_utc["tmax"]
        elif h in mc.HORIZONS:
            reason = "prévision ICON incomplète pour le jour UTC : ICON brut"
        tavg = raw_loc["tavg"] + d_avg
        tmin = raw_loc["tmin"] + d_min
        tmax = max(raw_loc["tmax"] + d_max, tmin)
        tavg = min(max(tavg, tmin), tmax)

        if rain is None:
            pe = ens_prob.get(ds)
            if pe is None:
                pr = raw_loc.get("precip") or 0.0
                pe = 85 if pr >= 5 else 65 if pr >= 2 else 45 if pr >= mc.RAIN_THRESHOLD_MM else 15 if pr > 0 else 5
            rain = float(pe)
        rain = round(rain)

        hours = adjust_hours(hours_primary[ds], raw_loc, tmin, tmax) if applied else hours_primary[ds]
        slots = build_slots(hours, rain)
        correction = round(d_avg, 1)
        days_hourly.append({
            "date": ds, "day_label": DAY_LABELS[k], "indicative": k >= 3,
            "ml_correction": correction,
            "method": reason,
            "summary": {"temp_min": round(tmin, 1), "temp_max": round(tmax, 1),
                        "precip_sum": round(sum(s["precipitation"] for s in slots), 1), "rain_prob": rain},
            "periods": build_periods(slots),
            "slots": slots,
        })
        log(f"   {ds} {DAY_LABELS[k]:13s} {tmin:5.1f}–{tmax:4.1f} °C (moy {tavg:.1f}, ICON {raw_loc['tavg']:.1f}, "
            f"corr {correction:+.1f}) pluie {rain} % — {reason}")

        if k <= 2:
            met = metrics.get(str(h), {}).get("metrics", {}) if h in mc.HORIZONS else {}
            sfx = "corrected" if applied else "raw_primary"
            mm = [met.get(t, {}).get(f"mae_{sfx}") for t in ("tmin", "tmax")]
            ww = [met.get(t, {}).get(f"within_2c_{sfx}") for t in ("tmin", "tmax")]
            mae = round(sum(mm) / 2, 2) if None not in mm else None
            within = sum(ww) / 2 if None not in ww else None
            by_h = {x["hour"]: x["temperature"] for x in hours if x["temperature"] is not None}

            def per(hs):
                v = [by_h[x] for x in hs if x in by_h]
                return round(sum(v) / len(v), 1) if v else round(tavg, 1)
            risk = "low" if rain < 30 else ("medium" if rain < 60 else "high")
            days_ml.append({
                "date": ds, "day_name": DAY_NAMES_EN[target.weekday()], "day_number": k,
                "day_label": DAY_LABELS[k],
                "temperature": {"predicted": round(tavg, 1), "min_estimate": round(tmin, 1),
                                "max_estimate": round(tmax, 1)},
                "rain": {"will_rain": rain >= 50, "probability": rain},
                "confidence": round(within * 100) if within is not None else None,
                "expected_error_c": mae,
                "method": reason,
                "raw_nwp": {"model": mc.PRIMARY, "temp_avg": round(raw_loc["tavg"], 1),
                            "temp_min": round(raw_loc["tmin"], 1), "temp_max": round(raw_loc["tmax"], 1)},
                "periods": {
                    "p1": {"name": "Matin (04h-12h)", "temp_estimate": per(range(4, 12)), "rain_risk": risk},
                    "p2": {"name": "Après-midi (12h-20h)", "temp_estimate": per(range(12, 20)), "rain_risk": risk},
                    "p3": {"name": "Nuit (20h-04h)", "temp_estimate": per(list(range(20, 24)) + list(range(0, 4))), "rain_risk": risk},
                },
            })
            if raw_utc and h in mc.HORIZONS:
                # Vérification sur le jour UTC (même définition que la station)
                issued.append({"k": h, "date": ds, "tavg": round(raw_utc["tavg"] + d_avg, 2),
                               "tmin": round(raw_utc["tmin"] + d_min, 2), "tmax": round(raw_utc["tmax"] + d_max, 2),
                               "raw_tavg": round(raw_utc["tavg"], 2), "raw_tmin": round(raw_utc["tmin"], 2),
                               "raw_tmax": round(raw_utc["tmax"], 2), "rain_prob": rain, "applied": applied})

    if not days_hourly or not days_ml:
        log("❌ Aucun jour généré — abandon (les fichiers précédents restent en ligne)")
        sys.exit(1)

    perf = metrics.get("1", {}).get("metrics", {})
    generated = datetime.now(mc.TZ).isoformat(timespec="seconds")
    predictions = {
        "generated_at": generated,
        "model_version": (model or {}).get("trained_at", "aucun (ICON brut)"),
        "model_type": "mos_station_correction",
        "training_days": metrics.get("1", {}).get("n_days"),
        "forecasts": days_ml,
        "model_performance": {
            "temperature_accuracy": (f"±{(perf['tmin']['mae_corrected'] + perf['tmax']['mae_corrected']) / 2:.1f}°C"
                                     if perf.get("tmin") and perf.get("tmax") else "inconnue"),
            "rain_accuracy": (f"{perf['rain']['accuracy'] * 100:.0f}%" if perf.get("rain") else "inconnue"),
            "measured_on": "erreur moyenne min/max, jours non vus à l'entraînement (J+1)",
        },
    }
    atomic_write_json(PRED_FILE, predictions)
    atomic_write_json(HOURLY_FILE, {
        "generated_at": generated,
        "source": "ICON (Open-Meteo) corrigé par la station IVINEL2 (J0–J+2), ICON brut au-delà",
        "slot_hours": SLOT_SIZE,
        "days": days_hourly,
    })
    log("✅ predictions.json et predictions_hourly.json écrits")

    for path, name in ((PRED_FILE, "predictions.json"), (HOURLY_FILE, "predictions_hourly.json")):
        try:
            upload_legacy(path, name, log=log)
        except Exception as e:
            log(f"⚠️  Upload legacy {name} : {e}")
        upload_data(path, name, log=log)

    # Vérification après les envois : une erreur ici ne bloque jamais la publication.
    try:
        summary = update_verification(issued, station, utc_today)
        if summary:
            log(f"📏 Erreurs réellement mesurées depuis la mise en service : {summary}")
        upload_data(VERIF_FILE, "mos_verification.json", log=log)
    except Exception as e:
        log(f"⚠️  Vérification non mise à jour : {e}")


if __name__ == "__main__":
    main()
