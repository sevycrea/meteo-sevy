#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de récupération automatique des données météo
Station: IVINEL2 (Kap Sevy)
Collecte: HORAIRE (toutes les heures)
"""

import requests
import json
import math
import os
import sys
from datetime import datetime
import ftplib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftp_helpers import upload_data
from http_helpers import get_json_with_retry
from io_helpers import atomic_write_json

# ============================================
# CONFIGURATION
# ============================================

# Weather Underground API — credentials via variables d'environnement (GitHub Secrets)
API_KEY    = os.environ.get("WU_API_KEY", "")
STATION_ID = os.environ.get("WU_STATION_ID", "IVINEL2")
API_URL    = f"https://api.weather.com/v2/pws/observations/current?stationId={STATION_ID}&format=json&units=m&numericPrecision=decimal&apiKey={API_KEY}"

# Chemins — relatifs à la racine du repo
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE      = os.path.join(BASE_DIR, "data", "meteo_data_hourly.json")
REALTIME_FILE  = os.path.join(BASE_DIR, "data", "meteo_data_realtime.json")
BACKUP_DIR     = os.path.join(BASE_DIR, "data", "backup")
LOG_FILE       = os.path.join(BASE_DIR, "logs", "auto_wunderground_hourly.log")

# Combien d'heures de données granulaires (10-min) à conserver
REALTIME_RETENTION_HOURS = 48

# FTP — credentials via variables d'environnement (GitHub Secrets)
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
FTP_PATH = ""

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Écrire dans le fichier log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message)

def load_existing_data():
    """Charger les données existantes ou créer structure vide"""
    if os.path.exists(JSON_FILE):
        try:
            with open(JSON_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"⚠️ Erreur lecture JSON existant: {e}")
            return {}
    return {}

def fetch_current_data():
    """Récupérer les données actuelles depuis Weather Underground.

    Utilise le helper retry pour absorber les micro-coupures réseau de WU
    (3 tentatives avec backoff 2s/4s = ~6s max au lieu d'un trou de 15 min).
    """
    data = get_json_with_retry(API_URL, timeout=10, attempts=3, log=log)
    if data is None:
        log("❌ API Weather Underground inaccessible après 3 tentatives")
        return None

    observations = data.get('observations') or []
    if not observations:
        log("⚠️  Aucune observation dans la réponse WU")
        return None

    return observations[0]

# Bornes physiques plausibles pour Vinelz (Suisse). Toute valeur hors bornes
# est traitée comme None (sentinel API, capteur défaillant).
PHYSICAL_BOUNDS = {
    'temp':            (-40.0, 50.0),    # °C
    'humidity':        (0.0,   100.0),   # %
    'wind_speed':      (0.0,   200.0),   # km/h
    'wind_gust':       (0.0,   250.0),   # km/h
    'pressure':        (900.0, 1100.0),  # hPa (au niveau de la mer ; Vinelz ~430 m)
    'precip_rate':     (0.0,   500.0),   # mm/h
    'precip_total':    (0.0,   500.0),   # mm/jour
    'dewpt':           (-50.0, 40.0),    # °C
    'wind_dir':        (0.0,   360.0),   # degrés
    'uv':              (0.0,   15.0),    # index
    'solar_radiation': (0.0,   1500.0),  # W/m²
}

def extract_weather_data(obs):
    """Extraire les données météo pertinentes.

    IMPORTANT : on retourne `None` si :
      - le champ est absent/null côté API,
      - la valeur ne se convertit pas en nombre,
      - la valeur sort des bornes physiques plausibles (sentinel type -999).

    Sinon une seule obs ratée pollue les min/max/avg de toute la journée
    (bug zéros silencieux + bug sentinels).
    """
    metric = obs.get('metric', {})

    def _num(value, field):
        """Convertit en float, rejette NaN/inf, vérifie les bornes physiques.

        Retourne None si :
          - valeur null/non-convertible,
          - NaN ou inf (les comparaisons avec NaN sont toujours False
            donc on doit le rejeter explicitement, sinon il passe les bornes),
          - hors des bornes physiques plausibles.
        """
        if value is None:
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        if not math.isfinite(v):  # rejette NaN et ±inf
            log(f"⚠️  Valeur non finie pour {field}={v!r} — ignorée")
            return None
        lo, hi = PHYSICAL_BOUNDS.get(field, (float('-inf'), float('inf')))
        if v < lo or v > hi:
            log(f"⚠️  Valeur hors bornes pour {field}={v} (attendu [{lo}, {hi}]) — ignorée")
            return None
        return v

    return {
        'temp':            _num(metric.get('temp'),            'temp'),
        'humidity':        _num(obs.get('humidity'),           'humidity'),
        'wind_speed':      _num(metric.get('windSpeed'),       'wind_speed'),
        'wind_gust':       _num(metric.get('windGust'),        'wind_gust'),
        'pressure':        _num(metric.get('pressure'),        'pressure'),
        'precip_rate':     _num(metric.get('precipRate'),      'precip_rate'),
        'precip_total':    _num(metric.get('precipTotal'),     'precip_total'),
        'dewpt':           _num(metric.get('dewpt'),           'dewpt'),
        'wind_dir':        _num(obs.get('winddir'),            'wind_dir'),
        'uv':              _num(obs.get('uv'),                 'uv'),
        'solar_radiation': _num(obs.get('solarRadiation'),     'solar_radiation'),
        'timestamp':       obs.get('obsTimeLocal', '')
    }

def update_hourly_data(all_data, current_data):
    """Ajouter les données horaires à la structure.

    PRINCIPE : on ne met JAMAIS à jour un agrégat daily (min/max/sum) avec
    une valeur None. Si la mesure est manquante, on saute simplement
    ce champ et on log un warning. Sinon une seule obs incomplète
    contamine tout le résumé du jour.
    """
    now = datetime.now()
    date_key = now.strftime("%Y-%m-%d")
    hour_key = now.strftime("%H:00")

    temp     = current_data.get('temp')
    rain     = current_data.get('precip_total')
    gust     = current_data.get('wind_gust')
    pressure = current_data.get('pressure')
    humidity = current_data.get('humidity')

    # Créer la structure du jour si elle n'existe pas — uniquement les champs
    # qui ont une vraie valeur. Les agrégats seront initialisés lazy plus bas.
    if date_key not in all_data:
        all_data[date_key] = {
            'hourly': {},
            'daily': {}
        }

    daily = all_data[date_key]['daily']

    # --- Snapshot horaire HH:00 -------------------------------------------
    # Sur le snapshot, on tolère 0 par défaut pour l'affichage, mais on logue
    # les champs manquants pour diagnostic.
    missing = [k for k in ('temp', 'humidity', 'wind_speed', 'pressure') if current_data.get(k) is None]
    if missing:
        log(f"⚠️  Champs manquants dans l'obs WU : {missing} — agrégats daily non mis à jour pour ces champs")

    def _disp(key, default=0.0):
        v = current_data.get(key)
        return float(v) if v is not None else default

    all_data[date_key]['hourly'][hour_key] = {
        'temp':     round(_disp('temp'),         1),
        'hum':      round(_disp('humidity'),     0),
        'wind':     round(_disp('wind_speed'),   1),
        'gust':     round(_disp('wind_gust'),    1),
        'wind_dir': int(_disp('wind_dir')),
        'pressure': round(_disp('pressure'),     1),
        'rain':     round(_disp('precip_total'), 1),
        'timestamp': current_data.get('timestamp', '')
    }

    # --- Agrégats daily (uniquement si la valeur est valide) --------------
    if temp is not None:
        daily['temp_min']   = min(daily.get('temp_min', temp),    temp)
        daily['temp_max']   = max(daily.get('temp_max', temp),    temp)
        daily['temp_sum']   = daily.get('temp_sum', 0)   + temp
        daily['temp_count'] = daily.get('temp_count', 0) + 1
        daily['temp_avg']   = round(daily['temp_sum'] / daily['temp_count'], 1)

    if rain is not None:
        # precipTotal est cumulatif jour → on prend le max plutôt que la somme.
        daily['rain_total'] = max(daily.get('rain_total', rain), rain)

    if gust is not None:
        daily['wind_max'] = max(daily.get('wind_max', gust), gust)

    if pressure is not None:
        daily['pressure_sum']   = daily.get('pressure_sum', 0)   + pressure
        daily['pressure_count'] = daily.get('pressure_count', 0) + 1
        daily['pressure_avg']   = round(daily['pressure_sum'] / daily['pressure_count'], 1)

    if humidity is not None:
        daily['humidity_sum']   = daily.get('humidity_sum', 0)   + humidity
        daily['humidity_count'] = daily.get('humidity_count', 0) + 1
        daily['humidity_avg']   = round(daily['humidity_sum'] / daily['humidity_count'], 0)

    return all_data

def cleanup_old_data(all_data, keep_days=90):
    """Garder seulement les X derniers jours"""
    dates = sorted(all_data.keys())
    if len(dates) > keep_days:
        for old_date in dates[:-keep_days]:
            del all_data[old_date]
            log(f"🗑️ Suppression ancienne date: {old_date}")
    return all_data

def save_json(data):
    """Sauvegarder le JSON de façon atomique (.tmp + os.replace).

    Évite qu'un crash mid-write laisse un fichier tronqué qui empoisonne
    les runs suivants (load_existing_data() lirait du JSON corrompu).
    """
    atomic_write_json(JSON_FILE, data)
    log(f"✅ JSON sauvegardé: {JSON_FILE}")

def update_realtime_data(current_data):
    """Conserve les mesures fines (10-min) sur les dernières 24h.
    Permet à detect_events.py de faire de la détection sub-horaire
    (front froid, chute pression, rafales) avec une fenêtre glissante précise.
    """
    from datetime import datetime, timedelta
    realtime = {}
    if os.path.exists(REALTIME_FILE):
        try:
            with open(REALTIME_FILE, 'r', encoding='utf-8') as f:
                realtime = json.load(f)
        except Exception as e:
            log(f"⚠️  Realtime corrupted, réinitialisation : {e}")
            realtime = {}

    # Ajouter la mesure courante avec clé "YYYY-MM-DD HH:MM".
    # Les champs None deviennent null dans le JSON (pas 0) → l'app/site
    # peuvent afficher "—" au lieu d'une fausse valeur.
    now = datetime.now()
    key = now.strftime("%Y-%m-%d %H:%M")

    def _rt(field, ndigits=1):
        v = current_data.get(field)
        if v is None:
            return None
        try:
            return round(float(v), ndigits)
        except (TypeError, ValueError):
            return None

    def _rt_int(field):
        v = current_data.get(field)
        if v is None:
            return None
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return None

    realtime[key] = {
        'temp':      _rt('temp',         1),
        'hum':       _rt('humidity',     0),
        'wind':      _rt('wind_speed',   1),
        'gust':      _rt('wind_gust',    1),
        'wind_dir':  _rt_int('wind_dir'),
        'pressure':  _rt('pressure',     1),
        'rain':      _rt('precip_total', 1),
        'timestamp': current_data.get('timestamp', ''),
    }

    # Trim : on ne garde que les dernières REALTIME_RETENTION_HOURS heures
    cutoff = now - timedelta(hours=REALTIME_RETENTION_HOURS)
    cutoff_key = cutoff.strftime("%Y-%m-%d %H:%M")
    keys_to_keep = [k for k in realtime.keys() if k >= cutoff_key]
    trimmed = {k: realtime[k] for k in sorted(keys_to_keep)}

    # Écriture atomique pour éviter qu'un crash laisse le fichier tronqué
    # (detect_events.py le lit comme fenêtre glissante 24h).
    atomic_write_json(REALTIME_FILE, trimmed)
    log(f"✅ Realtime mis à jour : {len(trimmed)} points sur {REALTIME_RETENTION_HOURS}h ({key})")

def backup_json():
    """Créer une sauvegarde du JSON"""
    if not os.path.exists(JSON_FILE):
        return
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = f"{BACKUP_DIR}/meteo_data_{timestamp}.json"
    
    try:
        import shutil
        shutil.copy2(JSON_FILE, backup_file)
        log(f"💾 Backup créé: {backup_file}")
        
        # Garder seulement les 10 derniers backups
        backups = sorted([f for f in os.listdir(BACKUP_DIR) if f.startswith('meteo_data_')])
        if len(backups) > 10:
            for old_backup in backups[:-10]:
                os.remove(os.path.join(BACKUP_DIR, old_backup))
    except Exception as e:
        log(f"⚠️ Erreur backup: {e}")

def upload_to_ftp():
    """Uploader le JSON vers WordPress via FTP (atomique).

    Utilise upload_legacy + upload_data du module ftp_helpers, qui font
    chacun un upload atomique (STOR vers .tmp, DELE, RNFR/RNTO).
    Aucun risque de JSON tronqué exposé publiquement.
    """
    if FTP_HOST == "ftp.votreserveur.com" or not FTP_HOST:
        log("⚠️ FTP non configuré - upload ignoré")
        return

    # Import local pour éviter une dépendance dure si le module n'est pas dispo
    from ftp_helpers import upload_legacy

    # Hourly (utilisé par le frontend — historique 90 jours)
    try:
        upload_legacy(JSON_FILE, 'meteo_data_hourly.json', log=log)
    except Exception as e:
        log(f"❌ Upload legacy meteo_data_hourly.json échoué: {e}")

    # Realtime (utilisé par detect_events — fenêtre glissante 24h)
    if os.path.exists(REALTIME_FILE):
        try:
            upload_legacy(REALTIME_FILE, 'meteo_data_realtime.json', log=log)
        except Exception as e:
            log(f"❌ Upload legacy meteo_data_realtime.json échoué: {e}")

    # Double upload vers data.sevy-creations.net (best-effort, ne casse pas si KO)
    upload_data(JSON_FILE, 'meteo_data_hourly.json', log=log)
    if os.path.exists(REALTIME_FILE):
        upload_data(REALTIME_FILE, 'meteo_data_realtime.json', log=log)

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 60)
    log("🚀 Démarrage collecte horaire")
    
    # 1. Charger données existantes
    all_data = load_existing_data()
    log(f"📂 Données existantes: {len(all_data)} jours")
    
    # 2. Récupérer données actuelles
    obs = fetch_current_data()
    if not obs:
        log("❌ Impossible de récupérer les données - abandon")
        return
    
    current_data = extract_weather_data(obs)
    t_disp = f"{current_data['temp']}°C" if current_data['temp'] is not None else "—"
    h_disp = f"{current_data['humidity']}%" if current_data['humidity'] is not None else "—"
    log(f"📡 Données reçues: {t_disp}, {h_disp}")

    # Validation : si AUCUN champ critique n'a une valeur → l'API a renvoyé
    # une obs vide, on abandonne pour ne rien écraser.
    critical = [current_data.get(k) for k in ('temp', 'humidity', 'pressure')]
    if all(v is None for v in critical):
        log("❌ Obs WU vide (tous les champs critiques sont null) — abandon pour ne pas polluer le JSON")
        return
    
    # 3. Mettre à jour avec les données horaires (snapshot HH:00)
    all_data = update_hourly_data(all_data, current_data)

    # 3.bis Conserver les mesures sub-horaires (10-min) sur les 24 dernières heures
    update_realtime_data(current_data)

    # 4. Nettoyer les anciennes données
    all_data = cleanup_old_data(all_data, keep_days=90)

    # 5. Sauvegarder
    save_json(all_data)
    
    # 6. Backup (une fois par jour à minuit)
    if datetime.now().hour == 0:
        backup_json()
    
    # 7. Upload FTP
    upload_to_ftp()
    
    log("✅ Collecte horaire terminée")
    log("=" * 60)

if __name__ == "__main__":
    main()
