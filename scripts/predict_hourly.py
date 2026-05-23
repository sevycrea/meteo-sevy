#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Prévisions par créneaux de 2 heures — 7 jours
Sources :
  - NWP horaire (Open-Meteo / MetNo) comme base
  - Correction locale ML : décalage entre T_quotidienne fusionnée et T_NWP
Sortie : data/json/predictions_hourly.json
"""

import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftp_helpers import upload_data
from io_helpers import atomic_write_json

# ============================================
# CONFIGURATION (chemins relatifs au repo)
# ============================================

BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR    = os.path.join(BASE_DIR, "data", "json")
NWP_FILE    = os.path.join(DATA_DIR, "nwp_forecast.json")
PRED_FILE   = os.path.join(DATA_DIR, "predictions.json")
# Fallback : predictions.json est aussi dans data/ (multihorizon)
PRED_FILE_ALT = os.path.join(BASE_DIR, "data", "predictions.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "predictions_hourly.json")
LOG_FILE    = os.path.join(BASE_DIR, "logs", "predictions_hourly.log")

# FTP via variables d'environnement (GitHub Actions secrets)
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")

SLOT_SIZE = 2   # heures par créneau

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
# CHARGEMENT
# ============================================

def load_nwp():
    try:
        with open(NWP_FILE, 'r', encoding='utf-8') as f:
            raw = json.load(f)
        fc = raw.get('forecasts', {})
        log(f"✅ NWP chargé ({len(fc)} jours)")
        return fc
    except Exception as e:
        log(f"❌ NWP non chargé : {e}")
        return {}

def load_ml_predictions():
    # Essai chemin principal puis chemin alternatif
    for path in (PRED_FILE, PRED_FILE_ALT):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            preds = {fc['date']: fc for fc in raw.get('forecasts', [])}
            log(f"✅ Prévisions ML chargées depuis {os.path.basename(path)} ({len(preds)} jours)")
            return preds
        except Exception:
            continue
    log("⚠️  Prévisions ML introuvables — corrections désactivées")
    return {}

# ============================================
# CRÉNEAUX DE 2H
# ============================================

def build_slots(hourly_data, ml_correction, nwp_day_rain_prob):
    by_hour = {h['hour']: h for h in hourly_data}

    slots = []
    for start in range(0, 24, SLOT_SIZE):
        end = start + SLOT_SIZE
        label = f"{start:02d}h–{end:02d}h"

        hours_in_slot = [by_hour[h] for h in range(start, end) if h in by_hour]
        if not hours_in_slot:
            continue

        temps    = [h['temperature']   for h in hours_in_slot if h['temperature']  is not None]
        precips  = [h['precipitation'] for h in hours_in_slot if h['precipitation'] is not None]
        clouds   = [h['cloud_cover']   for h in hours_in_slot if h['cloud_cover']   is not None]
        winds    = [h['wind_speed']    for h in hours_in_slot if h['wind_speed']     is not None]
        pressures= [h['pressure']      for h in hours_in_slot if h['pressure']       is not None]

        temp_avg     = round(sum(temps) / len(temps) + ml_correction, 1) if temps else None
        precip_sum   = round(sum(precips), 1) if precips else 0.0
        cloud_avg    = round(sum(clouds) / len(clouds))            if clouds   else None
        wind_avg     = round(sum(winds) / len(winds), 1)           if winds    else None
        pressure_avg = round(sum(pressures) / len(pressures), 1)   if pressures else None

        if precip_sum > 2.0:
            rain_prob = min(100, int(nwp_day_rain_prob * 1.1))
        elif precip_sum > 0.5:
            rain_prob = int(nwp_day_rain_prob * 0.8)
        elif precip_sum > 0.0:
            rain_prob = int(nwp_day_rain_prob * 0.5)
        else:
            rain_prob = max(0, int(nwp_day_rain_prob * 0.15))

        if precip_sum > 2.0:
            icon = "🌧️"
        elif precip_sum > 0.1:
            icon = "🌦️"
        elif cloud_avg is not None and cloud_avg > 75:
            icon = "☁️"
        elif cloud_avg is not None and cloud_avg > 40:
            icon = "⛅"
        else:
            icon = "☀️"

        slots.append({
            'time_start':  f"{start:02d}:00",
            'time_end':    f"{end:02d}:00",
            'label':       label,
            'icon':        icon,
            'temperature': temp_avg,
            'precipitation': precip_sum,
            'rain_prob':   rain_prob,
            'cloud_cover': cloud_avg,
            'wind_speed':  wind_avg,
            'pressure':    pressure_avg,
        })

    return slots


def build_periods(slots):
    """Agrège les créneaux 2h en 3 périodes (Matin / Après-midi / Nuit).

    Source UNIQUE et cohérente avec summary + slots : tout vient du NWP corrigé.
    Évite l'incohérence d'avant (périodes issues d'un modèle ML séparé cassé
    qui contredisait le résumé du jour).

    Découpage (heure de début du créneau) :
      - Matin      : 06h–12h
      - Après-midi : 12h–20h
      - Nuit       : 20h–06h
    """
    def _dominant_icon(sel):
        # Icône la plus "sévère" présente dans la période (pluie > nuages > soleil).
        order = ["🌧️", "🌦️", "☁️", "⛅", "☀️"]
        present = [s['icon'] for s in sel if s.get('icon')]
        for ic in order:
            if ic in present:
                return ic
        return present[0] if present else "☀️"

    def _agg(start_hours):
        sel = [s for s in slots if int(s['time_start'][:2]) in start_hours]
        temps = [s['temperature'] for s in sel if s['temperature'] is not None]
        rains = [s['rain_prob']   for s in sel if s['rain_prob']   is not None]
        if not temps:
            return None
        rp = max(rains) if rains else 0
        # Niveau de risque de pluie lisible (cohérent avec le % réel)
        if rp >= 60:   risk = "élevé"
        elif rp >= 30: risk = "modéré"
        else:          risk = "faible"
        return {
            'temp':      round(sum(temps) / len(temps), 1),
            'rain_prob': rp,
            'rain_risk': risk,
            'icon':      _dominant_icon(sel),
        }

    return {
        'matin':      {'name': 'Matin (06h–12h)',      **( _agg([6, 8, 10])           or {})},
        'apres_midi': {'name': 'Après-midi (12h–20h)', **( _agg([12, 14, 16, 18])     or {})},
        'nuit':       {'name': 'Nuit (20h–06h)',       **( _agg([20, 22, 0, 2, 4])    or {})},
    }

# ============================================
# GÉNÉRATION
# ============================================

def generate_hourly(nwp, ml_preds):
    DAY_LABELS = [
        "Aujourd'hui", "Demain", "Après-demain",
        "J+3", "J+4", "J+5", "J+6"
    ]

    days_output = []

    # Ne garder que les jours à partir d'aujourd'hui — protège contre un NWP
    # obsolète qui contiendrait encore des dates passées.
    today_iso = datetime.now().strftime("%Y-%m-%d")
    future_nwp = {d: v for d, v in nwp.items() if d >= today_iso}
    log(f"📆 Jours futurs disponibles dans le NWP : {len(future_nwp)} (à partir de {today_iso})")

    for i, (date_str, nwp_day) in enumerate(sorted(future_nwp.items())[:7]):
        hourly_data = nwp_day.get('hourly', [])
        if not hourly_data:
            log(f"⚠️  Pas de données horaires pour {date_str}")
            continue

        ml_pred = ml_preds.get(date_str)
        if ml_pred:
            t_ml = ml_pred['temperature']['predicted']
            t_nwp_avg = nwp_day.get('temp_avg') or t_ml
            raw_correction = round(t_ml - t_nwp_avg, 2)
            # Plafonner la correction ML à ±2°C : le NWP MetNo brut est
            # généralement précis à ±1-2°C. Une correction plus grande indique
            # un modèle ML mal calibré (entraîné sur saison différente, etc.).
            # On clamp pour éviter qu'un ML aberrant tire toutes les prévisions
            # horaires hors de la réalité (cas du 2026-05-09 : correction -6°C
            # alors que la réalité confirmait le NWP brut).
            ML_CORRECTION_CAP = 2.0
            if abs(raw_correction) > ML_CORRECTION_CAP:
                ml_correction = ML_CORRECTION_CAP if raw_correction > 0 else -ML_CORRECTION_CAP
                log(f"⚠️  Correction ML brute {raw_correction:+.2f}°C plafonnée à {ml_correction:+.1f}°C "
                    f"(ML={t_ml}° vs NWP_avg={t_nwp_avg}°)")
            else:
                ml_correction = raw_correction
        else:
            ml_correction = 0.0

        nwp_rain_prob = nwp_day.get('rain_prob', 0)
        slots = build_slots(hourly_data, ml_correction, nwp_rain_prob)

        label = DAY_LABELS[i] if i < len(DAY_LABELS) else f"J+{i}"
        indicative = i >= 3

        slot_temps = [s['temperature'] for s in slots if s['temperature'] is not None]
        day_temp_min = min(slot_temps) if slot_temps else nwp_day.get('temp_min')
        day_temp_max = max(slot_temps) if slot_temps else nwp_day.get('temp_max')
        day_precip   = round(sum(s['precipitation'] for s in slots), 1)

        days_output.append({
            'date':          date_str,
            'day_label':     label,
            'indicative':    indicative,
            'ml_correction': ml_correction,
            'summary': {
                'temp_min':    day_temp_min,
                'temp_max':    day_temp_max,
                'precip_sum':  day_precip,
                'rain_prob':   nwp_rain_prob,
            },
            'periods': build_periods(slots),
            'slots': slots,
        })

        correction_str = f"  (correction locale {ml_correction:+.1f}°C)" if abs(ml_correction) >= 0.5 else ""
        log(f"   {date_str} {label}: {day_temp_min:.0f}–{day_temp_max:.0f}°C  "
            f"précip {day_precip}mm  {len(slots)} créneaux{correction_str}")

    return days_output

# ============================================
# SAUVEGARDE + FTP
# ============================================

def save(days_output):
    output = {
        'generated_at': datetime.now().isoformat(),
        'source':       'NWP Open-Meteo/MetNo + correction ML locale',
        'slot_hours':   SLOT_SIZE,
        'days':         days_output,
    }
    atomic_write_json(OUTPUT_FILE, output)
    log(f"✅ predictions_hourly.json sauvegardé ({len(days_output)} jours)")

def upload():
    if not (FTP_HOST and FTP_USER and FTP_PASS):
        log("⚠️  FTP non configuré (env vars manquants) — upload ignoré")
        return
    try:
        import ftplib
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        with open(OUTPUT_FILE, 'rb') as f:
            ftp.storbinary('STOR predictions_hourly.json', f)
        ftp.quit()
        log("✅ predictions_hourly.json uploadé sur le serveur")

        # Double upload vers data.sevy-creations.net (best-effort)
        upload_data(OUTPUT_FILE, 'predictions_hourly.json', log=log)
    except Exception as e:
        log(f"⚠️  Upload FTP échoué : {e}")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 60)
    log("⏰ PRÉVISIONS HORAIRES (créneaux 2h) — 7 jours")
    log("=" * 60)

    nwp      = load_nwp()
    ml_preds = load_ml_predictions()

    if not nwp:
        log("❌ Données NWP manquantes — abandon (exit 1)")
        # exit 1 plutôt que return : sinon le workflow voit success et le user
        # croit que les prévisions horaires sont à jour alors qu'elles ne sont
        # pas mises à jour (ou pire, basées sur un NWP périmé en cache).
        sys.exit(1)

    log("")
    log("📅 Génération des créneaux :")
    days_output = generate_hourly(nwp, ml_preds)

    if not days_output:
        log("❌ Aucun jour futur généré — vérifier la fraîcheur du NWP")
        return

    save(days_output)
    upload()

    log("")
    log("=" * 60)
    if days_output:
        today = days_output[0]
        log(f"📋 Détail Aujourd'hui ({today['date']}) :")
        for s in today['slots']:
            rain_str = f"  🌧️ {s['precipitation']}mm" if s['precipitation'] > 0 else ''
            log(f"   {s['label']}  {s['icon']}  {s['temperature']}°C"
                f"  vent {s['wind_speed']}km/h{rain_str}")
    log("=" * 60)

if __name__ == "__main__":
    main()
