#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Détection d'Événements Météo Extrêmes — v2 (orages + temps réel)

Combine 3 stratégies de détection :
1. **Temps réel** (station IVINEL2) : analyse des dernières heures pour détecter
   les signes immédiats d'orage à proximité (chute T°, saut humidité, chute
   pression, rafales, pluie locale).
2. **NWP horaire** : examine les heures à venir du modèle MetNo pour
   anticiper les pics de précipitations et de vent.
3. **Prévisions journalières** (ML+NWP) : alertes "long terme" sur 7 jours
   (canicule, gel, pluie soutenue, vent fort).

Tous les alertes vont dans `data/alerts_history.json` puis sont publiées sur
le ticker du site via export_to_ftp.py → alerts.json.
"""

import json
import os
import subprocess
from datetime import datetime, timedelta

# ============================================
# CONFIGURATION
# ============================================
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDICTIONS_FILE = os.path.join(BASE_DIR, "data", "predictions.json")
DATA_FILE        = os.path.join(BASE_DIR, "data", "meteo_data_enriched.json")
HOURLY_FILE      = os.path.join(BASE_DIR, "data", "meteo_data_hourly.json")
REALTIME_FILE    = os.path.join(BASE_DIR, "data", "meteo_data_realtime.json")
NWP_FILE         = os.path.join(BASE_DIR, "data", "nwp_forecast.json")
NWP_FILE_ALT     = os.path.join(BASE_DIR, "data", "json", "nwp_forecast.json")
EVENTS_LOG       = os.path.join(BASE_DIR, "logs", "events.log")
ALERTS_HISTORY   = os.path.join(BASE_DIR, "data", "alerts_history.json")

os.makedirs(os.path.dirname(EVENTS_LOG), exist_ok=True)
os.makedirs(os.path.dirname(ALERTS_HISTORY), exist_ok=True)

# ============================================
# SEUILS DE DÉTECTION (Vinelz, Suisse)
# ============================================
THRESHOLDS = {
    # Prévisions journalières (long terme)
    'heat_wave':       {'high': 30.0, 'extreme': 35.0},
    'cold_wave':       {'low': 0.0,   'extreme_low': -10.0},
    'heavy_rain_day':  {'mm_warning': 15.0, 'mm_extreme': 30.0},   # cumul jour
    'rain_prob_high':  {'warning': 70, 'critical': 85},            # %
    'strong_wind_day': {'gust_warning': 40, 'gust_storm': 70},     # km/h
    # Temps réel (station, dernières heures)
    'realtime': {
        'temp_drop_2h':       3.0,    # °C
        'humidity_jump_2h':   15,     # %
        'pressure_drop_1h':   2.0,    # hPa
        'pressure_drop_3h':   4.0,    # hPa
        'gust_warning':       40,     # km/h
        'gust_critical':      60,     # km/h
        'rain_3h_warning':    3.0,    # mm cumulés sur 3h
        'rain_3h_critical':   8.0,    # mm cumulés
    },
    # NWP horaire (heures à venir)
    'nwp_upcoming': {
        'precip_per_hour_warning':  2.0,   # mm/h
        'precip_per_hour_extreme':  5.0,   # mm/h
        'wind_warning':             40,    # km/h
        'wind_storm':               70,    # km/h
        'horizon_hours':            12,    # combien d'heures à analyser
    },
    # Détection orage (codes WMO + CAPE)
    'thunderstorm': {
        'wmo_codes_thunder':       [95, 96, 99],  # 95=orage, 96=+grêle, 99=grêle violente
        'cape_warning':            1000,   # J/kg — instabilité significative
        'cape_critical':           2000,   # J/kg — instabilité forte (orages probables)
        'horizon_hours':           24,     # on regarde 24h pour anticiper
    },
}

# Codes WMO décodés (utile pour les messages)
WMO_NAMES = {
    95: "Orage",
    96: "Orage avec grêle légère",
    99: "Orage avec forte grêle",
}

# ============================================
# UTILITAIRES
# ============================================
def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{timestamp}] {message}\n"
    print(line.strip())
    with open(EVENTS_LOG, 'a', encoding='utf-8') as f:
        f.write(line)

def send_notification(title, message, sound="Glass"):
    try:
        script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
        subprocess.run(['osascript', '-e', script], check=True, timeout=5)
        log(f"🔔 Notification : {title}")
    except Exception as e:
        # Pas de macOS dans l'environnement GitHub Actions — pas grave
        pass

def load_json(path):
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"⚠️  Erreur chargement {path}: {e}")
        return None

def load_predictions():     return load_json(PREDICTIONS_FILE)
def load_hourly_station():  return load_json(HOURLY_FILE)
def load_realtime_station():
    """Mesures sub-horaires (10-min) — fenêtre glissante 24h.
    Si dispo, c'est BEAUCOUP plus précis pour la détection que les
    snapshots horaires (front froid détecté à 30 min près au lieu de 2h)."""
    return load_json(REALTIME_FILE)

def load_nwp():
    return load_json(NWP_FILE) or load_json(NWP_FILE_ALT)

def load_alerts_history():
    return load_json(ALERTS_HISTORY) or []

def save_alert(alert):
    history = load_alerts_history()
    # Anti-doublon : on évite de re-saver une alerte du même type pour la
    # même cible dans la dernière heure (évite de spammer le ticker).
    now = datetime.now()
    cutoff = now - timedelta(hours=1)
    recent_keys = set()
    for a in history:
        try:
            det = datetime.fromisoformat(a.get('detected_at', '1970-01-01'))
            if det > cutoff:
                key = (a.get('type'), a.get('target_hour'), a.get('date'))
                recent_keys.add(key)
        except Exception:
            pass
    new_key = (alert.get('type'), alert.get('target_hour'), alert.get('date'))
    if new_key in recent_keys:
        return  # déjà alerté il y a moins d'1h, on n'ajoute pas
    history.append(alert)
    history = history[-200:]
    with open(ALERTS_HISTORY, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def vinelz_today():
    """Date du jour à Vinelz (Europe/Zurich approx via heure locale)."""
    return datetime.now().strftime("%Y-%m-%d")

# ============================================
# 1. DÉTECTION TEMPS RÉEL (STATION IVINEL2)
# ============================================
def _flatten_realtime(realtime_data):
    """Convertit le dict realtime {YYYY-MM-DD HH:MM: ...} en liste triée
    par datetime. Retourne [(dt, key, record), ...]."""
    if not realtime_data:
        return []
    items = []
    for k, v in realtime_data.items():
        try:
            dt = datetime.strptime(k, "%Y-%m-%d %H:%M")
            items.append((dt, k, v))
        except ValueError:
            continue
    items.sort(key=lambda x: x[0])
    return items

def _fnum(v):
    try: return float(v)
    except (TypeError, ValueError): return None

def _analyze_window(records, window_label, source='hourly'):
    """Analyse une fenêtre temporelle de mesures (≥3 records, premier=plus
    ancien, dernier=le plus récent). Retourne la liste d'alertes détectées.
    Utilisé pour les deux modes : hourly fallback et realtime 10-min."""
    alerts = []
    if not records or len(records) < 3:
        return alerts

    R = THRESHOLDS['realtime']

    temps     = [_fnum(r.get('temp'))     for r in records]
    hums      = [_fnum(r.get('hum'))      for r in records]
    pressures = [_fnum(r.get('pressure')) for r in records]
    gusts     = [_fnum(r.get('gust'))     for r in records]
    rains     = [_fnum(r.get('rain'))     for r in records]

    # Fenêtre temporelle : ~2h en mode hourly (3 records), ~90 min en realtime
    win_label_hours = "2h" if source == 'hourly' else "1h30"

    # ── A) Front froid : chute T° + saut humidité simultanés ──
    if all(t is not None for t in temps) and all(h is not None for h in hums):
        temp_drop = temps[0] - temps[-1]
        hum_jump  = hums[-1] - hums[0]
        if temp_drop >= R['temp_drop_2h'] and hum_jump >= R['humidity_jump_2h']:
            alerts.append({
                'type': 'cold_front_realtime',
                'severity': 'warning',
                'window': window_label,
                'source': source,
                'message': (f"❄️🌧️ Front froid détecté · "
                            f"chute de {temp_drop:.1f}°C et hausse de {hum_jump:.0f}% d'humidité "
                            f"en {win_label_hours} ({window_label})"),
                'recommendation': "Orage probable à proximité — vigilance.",
                'metrics': {'temp_drop': round(temp_drop, 1),
                            'humidity_jump': round(hum_jump, 1)}
            })

    # ── B) Chute de pression rapide ──
    if all(p is not None for p in pressures):
        press_drop_short = pressures[-2] - pressures[-1] if len(pressures) >= 2 else 0
        press_drop_full  = pressures[0]  - pressures[-1]
        # Période courte = ~1h (hourly) ou ~10-30 min (realtime selon densité)
        short_label = "1h" if source == 'hourly' else "30 min"
        full_label  = "3h" if source == 'hourly' else "1h30"
        if press_drop_short >= R['pressure_drop_1h']:
            alerts.append({
                'type': 'pressure_drop_realtime',
                'severity': 'warning',
                'window': window_label,
                'source': source,
                'message': f"⚡ Chute de pression rapide · {press_drop_short:.1f} hPa en {short_label}",
                'recommendation': "Conditions instables — orage approchant possible.",
                'metrics': {'pressure_drop_short': round(press_drop_short, 1)}
            })
        elif press_drop_full >= R['pressure_drop_3h']:
            alerts.append({
                'type': 'pressure_drop_realtime',
                'severity': 'info',
                'window': window_label,
                'source': source,
                'message': f"📉 Pression en baisse · {press_drop_full:.1f} hPa en {full_label}",
                'recommendation': "Tendance à surveiller (perturbation possible).",
                'metrics': {'pressure_drop_full': round(press_drop_full, 1)}
            })

    # ── C) Rafales fortes ──
    if any(g is not None for g in gusts):
        gust_max = max((g for g in gusts if g is not None), default=0)
        if gust_max >= R['gust_critical']:
            alerts.append({
                'type': 'wind_gust_realtime',
                'severity': 'critical',
                'window': window_label,
                'source': source,
                'message': f"💨 Rafale forte · {gust_max:.0f} km/h",
                'recommendation': "Sécurisez les objets extérieurs.",
                'metrics': {'gust_max': round(gust_max, 1)}
            })
        elif gust_max >= R['gust_warning']:
            alerts.append({
                'type': 'wind_gust_realtime',
                'severity': 'warning',
                'window': window_label,
                'source': source,
                'message': f"💨 Vent soutenu · rafale {gust_max:.0f} km/h",
                'recommendation': "Attention au vent.",
                'metrics': {'gust_max': round(gust_max, 1)}
            })

    # ── D) Pluie locale ──
    if any(r is not None for r in rains):
        rain_cumul = sum(r for r in rains if r is not None)
        cumul_label = "3h" if source == 'hourly' else "1h30"
        if rain_cumul >= R['rain_3h_critical']:
            alerts.append({
                'type': 'local_rain_realtime',
                'severity': 'warning',
                'window': window_label,
                'source': source,
                'message': f"🌧️ Pluie soutenue · {rain_cumul:.1f} mm cumulés en {cumul_label}",
                'recommendation': "Précipitations actives — sols saturés possibles.",
                'metrics': {'rain_cumul': round(rain_cumul, 1)}
            })
        elif rain_cumul >= R['rain_3h_warning']:
            alerts.append({
                'type': 'local_rain_realtime',
                'severity': 'info',
                'window': window_label,
                'source': source,
                'message': f"🌧️ Pluie en cours · {rain_cumul:.1f} mm en {cumul_label}",
                'recommendation': "Précipitations actives.",
                'metrics': {'rain_cumul': round(rain_cumul, 1)}
            })

    return alerts

def realtime_check(hourly_station, realtime_station=None):
    """Détection temps réel des signes d'orage / front froid à partir
    des mesures station les plus récentes.

    - Si meteo_data_realtime.json dispo (10-min granularity) → fenêtre 90 min,
      détection beaucoup plus rapide (alerte ~10 min après début du front).
    - Sinon fallback sur meteo_data_hourly.json (3 dernières heures snapshots).
    """
    # Mode REALTIME (10-min granularity)
    if realtime_station:
        items = _flatten_realtime(realtime_station)
        if items:
            now = datetime.now()
            # Fenêtre 90 min glissante
            recent = [(dt, k, v) for (dt, k, v) in items
                      if (now - dt).total_seconds() <= 90 * 60]
            if len(recent) >= 4:
                first_key, last_key = recent[0][1], recent[-1][1]
                window_label = f"{first_key[-5:]}–{last_key[-5:]}"
                return _analyze_window([v for (_, _, v) in recent],
                                       window_label, source='realtime')

    # Mode FALLBACK (snapshots horaires)
    if not hourly_station:
        return []
    today = vinelz_today()
    today_data = hourly_station.get(today, {}).get('hourly', {})
    if not today_data or len(today_data) < 3:
        log(f"  ⏭  Temps réel : moins de 3 heures dispo pour {today} — skip")
        return []
    keys = sorted(today_data.keys())
    last3 = [today_data[k] for k in keys[-3:]]
    return _analyze_window(last3, f"{keys[-3]}–{keys[-1]}", source='hourly')

# ============================================
# 2. DÉTECTION NWP HORAIRE (HEURES À VENIR)
# ============================================
def nwp_upcoming_check(nwp_data):
    """Examine les prochaines heures du NWP MetNo pour anticiper les
    précipitations fortes ou les rafales."""
    alerts = []
    if not nwp_data:
        return alerts

    forecasts = nwp_data.get('forecasts', {})
    if not isinstance(forecasts, dict):
        return alerts

    today = vinelz_today()
    today_nwp = forecasts.get(today)
    if not today_nwp:
        return alerts

    hourly = today_nwp.get('hourly', [])
    if not hourly or len(hourly) < 24:
        return alerts

    now_hour = datetime.now().hour
    horizon = THRESHOLDS['nwp_upcoming']['horizon_hours']
    upcoming = hourly[now_hour:now_hour + horizon]
    if not upcoming:
        return alerts

    N = THRESHOLDS['nwp_upcoming']

    # ── Pic de précipitations dans les prochaines heures ──
    max_precip = 0
    max_precip_hour = None
    for i, hr in enumerate(upcoming):
        precip = hr.get('precipitation') or 0
        try: precip = float(precip)
        except (TypeError, ValueError): precip = 0
        if precip > max_precip:
            max_precip = precip
            max_precip_hour = (now_hour + i) % 24

    if max_precip >= N['precip_per_hour_extreme']:
        alerts.append({
            'type': 'precip_upcoming',
            'severity': 'critical',
            'target_hour': max_precip_hour,
            'date': today,
            'message': (f"🌧️⚡ Précipitations extrêmes prévues vers {max_precip_hour:02d}h · "
                        f"{max_precip:.1f} mm/h"),
            'recommendation': "Risque d'orage / de fortes pluies — restez prudent.",
            'metrics': {'precip_mm_h': round(max_precip, 2), 'hour': max_precip_hour}
        })
    elif max_precip >= N['precip_per_hour_warning']:
        alerts.append({
            'type': 'precip_upcoming',
            'severity': 'warning',
            'target_hour': max_precip_hour,
            'date': today,
            'message': (f"🌧️ Pluie forte prévue vers {max_precip_hour:02d}h · "
                        f"{max_precip:.1f} mm/h"),
            'recommendation': "Prévoyez un parapluie.",
            'metrics': {'precip_mm_h': round(max_precip, 2), 'hour': max_precip_hour}
        })

    # ── Pic de vent dans les prochaines heures ──
    max_wind = 0
    max_wind_hour = None
    for i, hr in enumerate(upcoming):
        w = hr.get('wind_speed') or 0
        try: w = float(w)
        except (TypeError, ValueError): w = 0
        if w > max_wind:
            max_wind = w
            max_wind_hour = (now_hour + i) % 24

    if max_wind >= N['wind_storm']:
        alerts.append({
            'type': 'wind_upcoming',
            'severity': 'critical',
            'target_hour': max_wind_hour,
            'date': today,
            'message': f"🌬️ Tempête prévue vers {max_wind_hour:02d}h · {max_wind:.0f} km/h",
            'recommendation': "Restez à l'abri, sécurisez les extérieurs.",
            'metrics': {'wind_kmh': round(max_wind, 1), 'hour': max_wind_hour}
        })
    elif max_wind >= N['wind_warning']:
        alerts.append({
            'type': 'wind_upcoming',
            'severity': 'warning',
            'target_hour': max_wind_hour,
            'date': today,
            'message': f"💨 Vent fort prévu vers {max_wind_hour:02d}h · {max_wind:.0f} km/h",
            'recommendation': "Attention au vent.",
            'metrics': {'wind_kmh': round(max_wind, 1), 'hour': max_wind_hour}
        })

    return alerts

# ============================================
# 2.bis DÉTECTION D'ORAGES (WMO + CAPE) — 24h à venir
# ============================================
def thunderstorm_check(nwp_data):
    """Examine les codes WMO et CAPE des prochaines 24h pour anticiper
    les orages.

    Critères :
      - WMO ∈ {95, 96, 99} → orage prévu (warning/critical selon code)
      - CAPE ≥ 1000 J/kg combinée à précip ou vent → risque convectif
      - CAPE ≥ 2000 J/kg → instabilité forte (alerte préventive)
    """
    alerts = []
    if not nwp_data:
        return alerts

    forecasts = nwp_data.get('forecasts', {})
    if not isinstance(forecasts, dict):
        return alerts

    today = vinelz_today()
    T = THRESHOLDS['thunderstorm']

    # On scanne aujourd'hui + demain (24h glissantes)
    candidate_dates = sorted(forecasts.keys())
    if today in candidate_dates:
        idx = candidate_dates.index(today)
        scan_dates = candidate_dates[idx:idx + 2]
    else:
        scan_dates = candidate_dates[:2]

    now_hour = datetime.now().hour
    horizon = T['horizon_hours']
    hours_scanned = 0

    found_thunder = []   # [(date, hour, wmo, cape, precip)]
    found_high_cape = []

    for d_idx, date in enumerate(scan_dates):
        day = forecasts.get(date, {})
        hourly = day.get('hourly', [])
        if not hourly:
            continue
        # Pour aujourd'hui : on ne regarde que les heures à venir
        # Pour demain : toutes les heures
        for hr in hourly:
            h = hr.get('hour')
            if h is None:
                continue
            if d_idx == 0 and h < now_hour:
                continue
            if hours_scanned >= horizon:
                break

            wmo = hr.get('weathercode')
            cape = hr.get('cape')
            precip = hr.get('precipitation') or 0

            try: wmo = int(wmo) if wmo is not None else None
            except (TypeError, ValueError): wmo = None
            try: cape = float(cape) if cape is not None else 0
            except (TypeError, ValueError): cape = 0
            try: precip = float(precip)
            except (TypeError, ValueError): precip = 0

            if wmo in T['wmo_codes_thunder']:
                found_thunder.append((date, h, wmo, cape, precip))
            elif cape >= T['cape_warning'] and (precip >= 0.5 or hr.get('wind_speed', 0) >= 25):
                found_high_cape.append((date, h, wmo, cape, precip))

            hours_scanned += 1
        if hours_scanned >= horizon:
            break

    # Construction des alertes
    if found_thunder:
        # On garde la plus précoce
        date, hour, wmo, cape, precip = found_thunder[0]
        wmo_label = WMO_NAMES.get(wmo, f"Code {wmo}")
        is_today = (date == today)
        when = f"vers {hour:02d}h" if is_today else f"demain vers {hour:02d}h"
        sev = 'critical' if wmo in (96, 99) else 'warning'
        emoji = "⚡⚡" if wmo == 99 else "⚡"
        alerts.append({
            'type': 'thunderstorm_upcoming',
            'severity': sev,
            'date': date,
            'target_hour': hour,
            'message': f"{emoji} {wmo_label} prévu {when} (NWP)",
            'recommendation': "Restez à l'abri pendant l'orage, attention à la foudre.",
            'metrics': {'wmo': wmo, 'cape': cape, 'precip_mm_h': precip}
        })

    if found_high_cape:
        date, hour, wmo, cape, precip = found_high_cape[0]
        is_today = (date == today)
        when = f"vers {hour:02d}h" if is_today else f"demain vers {hour:02d}h"
        sev = 'warning' if cape >= T['cape_critical'] else 'info'
        alerts.append({
            'type': 'instability_upcoming',
            'severity': sev,
            'date': date,
            'target_hour': hour,
            'message': f"⚠️ Atmosphère instable {when} · CAPE {cape:.0f} J/kg",
            'recommendation': "Risque d'averses orageuses ou de coups de vent.",
            'metrics': {'cape': cape, 'wmo': wmo}
        })

    return alerts

# ============================================
# 3. DÉTECTION JOURNALIÈRE (ML + NWP) — long terme 7j
# ============================================
def check_heat_wave(forecasts):
    out = []
    for f in forecasts:
        temp = f.get('temperature', {}).get('predicted')
        if temp is None: continue
        date = f.get('date'); label = f.get('day_label', date)
        if temp >= THRESHOLDS['heat_wave']['extreme']:
            out.append({'type': 'heat_wave_extreme', 'severity': 'critical', 'date': date, 'day_label': label,
                        'temperature': temp, 'message': f"🔥 CANICULE EXTRÊME : {temp}°C prévu {label}",
                        'recommendation': "Restez au frais, hydratez-vous abondamment."})
        elif temp >= THRESHOLDS['heat_wave']['high']:
            out.append({'type': 'heat_wave', 'severity': 'warning', 'date': date, 'day_label': label,
                        'temperature': temp, 'message': f"🌡️ Forte chaleur : {temp}°C prévu {label}",
                        'recommendation': "Évitez l'exposition au soleil aux heures chaudes."})
    return out

def check_cold_wave(forecasts):
    out = []
    for f in forecasts:
        t = f.get('temperature', {}); temp = t.get('predicted'); tmin = t.get('min_estimate')
        if temp is None: continue
        date = f.get('date'); label = f.get('day_label', date)
        if temp <= THRESHOLDS['cold_wave']['extreme_low']:
            out.append({'type': 'extreme_cold', 'severity': 'critical', 'date': date, 'day_label': label,
                        'temperature': temp, 'message': f"❄️ GRAND FROID : {temp}°C prévu {label}",
                        'recommendation': "Protégez-vous, attention aux canalisations."})
        elif tmin is not None and tmin <= THRESHOLDS['cold_wave']['low']:
            out.append({'type': 'frost', 'severity': 'warning', 'date': date, 'day_label': label,
                        'temperature_min': tmin, 'message': f"🧊 Risque de gel · min {tmin}°C {label}",
                        'recommendation': "Protégez les plantes, attention au verglas."})
    return out

def check_heavy_rain(forecasts, nwp_data):
    """Pluie forte journalière. Utilise probabilité ML + cumul NWP si dispo."""
    out = []
    nwp_forecasts = (nwp_data or {}).get('forecasts', {}) if isinstance(nwp_data, dict) else {}
    for f in forecasts:
        date = f.get('date'); label = f.get('day_label', date)
        rain = f.get('rain', {}); prob = rain.get('probability', 0) or 0
        # Quantité depuis NWP daily si dispo
        nwp_day = nwp_forecasts.get(date) if isinstance(nwp_forecasts, dict) else None
        cumul = (nwp_day or {}).get('precip_sum') if nwp_day else None

        # Niveau extrême si grosse quantité prévue OU proba très haute
        if cumul is not None and cumul >= THRESHOLDS['heavy_rain_day']['mm_extreme']:
            out.append({'type': 'heavy_rain_extreme', 'severity': 'critical', 'date': date, 'day_label': label,
                        'rain_mm': cumul, 'rain_probability': prob,
                        'message': f"🌧️⚡ Précipitations extrêmes · {cumul:.0f} mm prévus {label}",
                        'recommendation': "Risque d'inondations locales — vigilance."})
        elif cumul is not None and cumul >= THRESHOLDS['heavy_rain_day']['mm_warning']:
            out.append({'type': 'heavy_rain', 'severity': 'warning', 'date': date, 'day_label': label,
                        'rain_mm': cumul, 'rain_probability': prob,
                        'message': f"🌧️ Pluie forte · {cumul:.0f} mm prévus {label} (proba {prob}%)",
                        'recommendation': "Prévoyez un parapluie, possibles ruissellements."})
        elif prob >= THRESHOLDS['rain_prob_high']['critical']:
            out.append({'type': 'rain_likely', 'severity': 'warning', 'date': date, 'day_label': label,
                        'rain_probability': prob,
                        'message': f"🌧️ Pluie quasi certaine · {prob}% {label}",
                        'recommendation': "Prévoyez un parapluie."})
        elif prob >= THRESHOLDS['rain_prob_high']['warning']:
            out.append({'type': 'rain_likely', 'severity': 'info', 'date': date, 'day_label': label,
                        'rain_probability': prob,
                        'message': f"🌧️ Pluie probable · {prob}% {label}",
                        'recommendation': "Pensez à votre parapluie."})
    return out

def check_strong_wind(forecasts, nwp_data):
    """Vent fort journalier — utilise NWP daily (gust_max / wind_max) si dispo."""
    out = []
    nwp_forecasts = (nwp_data or {}).get('forecasts', {}) if isinstance(nwp_data, dict) else {}
    for f in forecasts:
        date = f.get('date'); label = f.get('day_label', date)
        nwp_day = nwp_forecasts.get(date) if isinstance(nwp_forecasts, dict) else None
        if not nwp_day: continue
        gust = nwp_day.get('gust_max') or nwp_day.get('wind_max') or 0
        try: gust = float(gust)
        except (TypeError, ValueError): continue

        T = THRESHOLDS['strong_wind_day']
        if gust >= T['gust_storm']:
            out.append({'type': 'storm_day', 'severity': 'critical', 'date': date, 'day_label': label,
                        'gust_kmh': gust,
                        'message': f"🌬️ Tempête · rafales jusqu'à {gust:.0f} km/h {label}",
                        'recommendation': "Restez à l'abri, sécurisez vos extérieurs."})
        elif gust >= T['gust_warning']:
            out.append({'type': 'strong_wind_day', 'severity': 'warning', 'date': date, 'day_label': label,
                        'gust_kmh': gust,
                        'message': f"💨 Vent fort · rafales jusqu'à {gust:.0f} km/h {label}",
                        'recommendation': "Attention au vent."})
    return out

def check_temperature_drop(forecasts):
    """Chute brutale de T° entre 2 jours consécutifs."""
    out = []
    for i in range(1, len(forecasts)):
        t1 = forecasts[i-1].get('temperature', {}).get('predicted')
        t2 = forecasts[i].get('temperature', {}).get('predicted')
        if t1 is None or t2 is None: continue
        drop = t1 - t2
        if drop >= 8:  # seuil légèrement abaissé
            date = forecasts[i].get('date'); label = forecasts[i].get('day_label', date)
            out.append({'type': 'temperature_drop', 'severity': 'info', 'date': date, 'day_label': label,
                        'temperature_drop': drop,
                        'message': f"📉 Chute de température · {drop:.1f}°C de moins entre aujourd'hui et {label}",
                        'recommendation': "Adaptez vos vêtements en conséquence."})
    return out

# ============================================
# MAIN
# ============================================
def detect_events():
    log("=" * 70)
    log("🔍 DÉTECTION D'ÉVÉNEMENTS MÉTÉO — v2 (orages + temps réel)")
    log("=" * 70)

    predictions = load_predictions()
    forecasts = (predictions or {}).get('forecasts', []) or []
    if isinstance(forecasts, dict):
        forecasts = list(forecasts.values())

    hourly_station   = load_hourly_station()
    realtime_station = load_realtime_station()
    nwp_data         = load_nwp()

    log(f"📊 Sources : prédictions={len(forecasts)}j · "
        f"hourly={'oui' if hourly_station else 'non'} · "
        f"realtime={'oui (' + str(len(realtime_station)) + ' pts)' if realtime_station else 'non'} · "
        f"NWP={'oui' if nwp_data else 'non'}")
    log("")

    all_alerts = []

    # 1. Temps réel
    mode = "realtime 10-min" if realtime_station else "hourly snapshots"
    log(f"⏱  Analyse temps réel (mode {mode})…")
    rt = realtime_check(hourly_station or {}, realtime_station)
    log(f"   → {len(rt)} alerte(s)")
    for a in rt: log(f"     • {a['message']}")
    all_alerts.extend(rt)

    # 2. NWP heures à venir
    log("🛰  Analyse NWP horaire (12 prochaines heures)…")
    nu = nwp_upcoming_check(nwp_data)
    log(f"   → {len(nu)} alerte(s)")
    for a in nu: log(f"     • {a['message']}")
    all_alerts.extend(nu)

    # 2.bis Orages (codes WMO 95-99 + CAPE) sur 24h
    log("⚡ Analyse d'orages (WMO + CAPE) sur 24h…")
    th = thunderstorm_check(nwp_data)
    log(f"   → {len(th)} alerte(s)")
    for a in th: log(f"     • {a['message']}")
    all_alerts.extend(th)

    # 3. Prévisions journalières
    log("📅 Analyse prévisions 7 jours (ML + NWP)…")
    daily = []
    daily.extend(check_heat_wave(forecasts))
    daily.extend(check_cold_wave(forecasts))
    daily.extend(check_heavy_rain(forecasts, nwp_data))
    daily.extend(check_strong_wind(forecasts, nwp_data))
    daily.extend(check_temperature_drop(forecasts))
    log(f"   → {len(daily)} alerte(s)")
    for a in daily: log(f"     • {a['message']}")
    all_alerts.extend(daily)

    # Résumé
    log("")
    log("=" * 70)
    log("📊 RÉSUMÉ")
    log("=" * 70)
    if all_alerts:
        crit = [a for a in all_alerts if a['severity'] == 'critical']
        warn = [a for a in all_alerts if a['severity'] == 'warning']
        info = [a for a in all_alerts if a['severity'] == 'info']
        log(f"⚠️  {len(all_alerts)} alerte(s) total — critique:{len(crit)} avert:{len(warn)} info:{len(info)}")

        # Sauvegarder + notifier
        for alert in all_alerts:
            alert['detected_at'] = datetime.now().isoformat()
            save_alert(alert)
            # Notif uniquement critique (évite spam macOS)
            if alert['severity'] == 'critical':
                title = alert['message'].split('·')[0].strip() if '·' in alert['message'] else alert['type']
                send_notification(title[:50], alert['message'][:120], sound="Basso")
    else:
        log("✅ Aucun événement détecté — conditions normales")
    log("")
    log("=" * 70)

def main():
    detect_events()

if __name__ == "__main__":
    main()
