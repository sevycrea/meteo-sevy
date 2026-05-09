#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de récupération automatique des données météo
Station: IVINEL2 (Kap Sevy)
Collecte: HORAIRE (toutes les heures)
"""

import requests
import json
import os
from datetime import datetime
import ftplib

# ============================================
# CONFIGURATION
# ============================================

# Weather Underground API — credentials via variables d'environnement (GitHub Secrets)
API_KEY    = os.environ.get("WU_API_KEY", "")
STATION_ID = os.environ.get("WU_STATION_ID", "IVINEL2")
API_URL    = f"https://api.weather.com/v2/pws/observations/current?stationId={STATION_ID}&format=json&units=m&apiKey={API_KEY}"

# Chemins — relatifs à la racine du repo
BASE_DIR       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JSON_FILE      = os.path.join(BASE_DIR, "data", "meteo_data_hourly.json")
REALTIME_FILE  = os.path.join(BASE_DIR, "data", "meteo_data_realtime.json")
BACKUP_DIR     = os.path.join(BASE_DIR, "data", "backup")
LOG_FILE       = os.path.join(BASE_DIR, "logs", "auto_wunderground_hourly.log")

# Combien d'heures de données granulaires (10-min) à conserver
REALTIME_RETENTION_HOURS = 24

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
    """Récupérer les données actuelles depuis Weather Underground"""
    try:
        response = requests.get(API_URL, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if 'observations' not in data or len(data['observations']) == 0:
            raise Exception("Aucune observation dans la réponse")
        
        obs = data['observations'][0]
        return obs
        
    except Exception as e:
        log(f"❌ Erreur API Weather Underground: {e}")
        return None

def extract_weather_data(obs):
    """Extraire les données météo pertinentes"""
    metric = obs.get('metric', {})
    
    return {
        'temp': metric.get('temp', 0),
        'humidity': obs.get('humidity', 0),
        'wind_speed': metric.get('windSpeed', 0),
        'wind_gust': metric.get('windGust', 0),
        'pressure': metric.get('pressure', 0),
        'precip_rate': metric.get('precipRate', 0),
        'precip_total': metric.get('precipTotal', 0),
        'dewpt': metric.get('dewpt', 0),
        'wind_dir': obs.get('winddir', 0),
        'uv': obs.get('uv', 0),
        'solar_radiation': obs.get('solarRadiation', 0),
        'timestamp': obs.get('obsTimeLocal', '')
    }

def update_hourly_data(all_data, current_data):
    """Ajouter les données horaires à la structure"""
    now = datetime.now()
    date_key = now.strftime("%Y-%m-%d")
    hour_key = now.strftime("%H:00")
    
    # Créer la structure du jour si elle n'existe pas
    if date_key not in all_data:
        all_data[date_key] = {
            'hourly': {},
            'daily': {
                'temp_min': current_data['temp'],
                'temp_max': current_data['temp'],
                'temp_sum': current_data['temp'],
                'temp_count': 1,
                'rain_total': current_data['precip_total'],
                'wind_max': current_data['wind_gust'],
                'pressure_sum': current_data['pressure'],
                'pressure_count': 1,
                'humidity_sum': current_data['humidity'],
                'humidity_count': 1
            }
        }
    
    # Ajouter les données de cette heure
    all_data[date_key]['hourly'][hour_key] = {
        'temp': round(current_data['temp'], 1),
        'hum': round(current_data['humidity'], 0),
        'wind': round(current_data['wind_speed'], 1),
        'gust': round(current_data['wind_gust'], 1),
        'pressure': round(current_data['pressure'], 1),
        'rain': round(current_data['precip_total'], 1),
        'timestamp': current_data['timestamp']
    }
    
    # Mettre à jour les statistiques quotidiennes
    daily = all_data[date_key]['daily']
    daily['temp_min'] = min(daily['temp_min'], current_data['temp'])
    daily['temp_max'] = max(daily['temp_max'], current_data['temp'])
    daily['temp_sum'] += current_data['temp']
    daily['temp_count'] += 1
    daily['rain_total'] = max(daily['rain_total'], current_data['precip_total'])
    daily['wind_max'] = max(daily['wind_max'], current_data['wind_gust'])
    daily['pressure_sum'] += current_data['pressure']
    daily['pressure_count'] += 1
    daily['humidity_sum'] += current_data['humidity']
    daily['humidity_count'] += 1
    
    # Calculer les moyennes
    daily['temp_avg'] = round(daily['temp_sum'] / daily['temp_count'], 1)
    daily['pressure_avg'] = round(daily['pressure_sum'] / daily['pressure_count'], 1)
    daily['humidity_avg'] = round(daily['humidity_sum'] / daily['humidity_count'], 0)
    
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
    """Sauvegarder le JSON"""
    os.makedirs(os.path.dirname(JSON_FILE), exist_ok=True)

    with open(JSON_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

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

    # Ajouter la mesure courante avec clé "YYYY-MM-DD HH:MM"
    now = datetime.now()
    key = now.strftime("%Y-%m-%d %H:%M")
    realtime[key] = {
        'temp':      round(current_data['temp'], 1),
        'hum':       round(current_data['humidity'], 0),
        'wind':      round(current_data['wind_speed'], 1),
        'gust':      round(current_data['wind_gust'], 1),
        'pressure':  round(current_data['pressure'], 1),
        'rain':      round(current_data['precip_total'], 1),
        'timestamp': current_data['timestamp'],
    }

    # Trim : on ne garde que les dernières REALTIME_RETENTION_HOURS heures
    cutoff = now - timedelta(hours=REALTIME_RETENTION_HOURS)
    cutoff_key = cutoff.strftime("%Y-%m-%d %H:%M")
    keys_to_keep = [k for k in realtime.keys() if k >= cutoff_key]
    trimmed = {k: realtime[k] for k in sorted(keys_to_keep)}

    with open(REALTIME_FILE, 'w', encoding='utf-8') as f:
        json.dump(trimmed, f, ensure_ascii=False, indent=2)
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
    """Uploader le JSON vers WordPress via FTP"""
    if FTP_HOST == "ftp.votreserveur.com" or not FTP_HOST:
        log("⚠️ FTP non configuré - upload ignoré")
        return

    try:
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        if FTP_PATH:
            ftp.cwd(FTP_PATH)

        # Hourly (utilisé par le frontend — historique 90 jours)
        with open(JSON_FILE, 'rb') as f:
            ftp.storbinary('STOR meteo_data_hourly.json', f)
        log("✅ Upload meteo_data_hourly.json")

        # Realtime (utilisé par detect_events — fenêtre glissante 24h)
        if os.path.exists(REALTIME_FILE):
            with open(REALTIME_FILE, 'rb') as f:
                ftp.storbinary('STOR meteo_data_realtime.json', f)
            log("✅ Upload meteo_data_realtime.json")

        ftp.quit()
        log("✅ Upload FTP terminé")

    except Exception as e:
        log(f"❌ Erreur FTP: {e}")

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
    log(f"📡 Données reçues: {current_data['temp']}°C, {current_data['humidity']}%")
    
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
