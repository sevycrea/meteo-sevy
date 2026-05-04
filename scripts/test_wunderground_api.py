#!/usr/bin/env python3
"""
Station Météo Kap Sevy - Automatisation via Weather Underground API
Récupère les données depuis Wunderground et met à jour WordPress automatiquement

Exécution : python3 auto_meteo_wunderground.py
"""
import os
import sys
import json
import requests
from datetime import datetime, timedelta
from ftplib import FTP
import time

# ══════════════════════════════════════════════════════════════
# CONFIGURATION
# ══════════════════════════════════════════════════════════════

# Weather Underground API
WU_API_KEY = "de1b65ccc1fd4d6d9b65ccc1fded6d93"
WU_STATION_ID = "IVINEL2"
WU_API_URL = "https://api.weather.com/v2/pws/observations/all/1day"

# Chemins locaux
DATA_DIR = "/Users/yves/Desktop/Meteo_Backups/Data"
JSON_OUTPUT = os.path.join(DATA_DIR, "meteo_data.json")
LOG_FILE = os.path.join(DATA_DIR, "auto_update_wunderground.log")

# FTP WordPress
FTP_HOST = "ig6i34.ftp.infomaniak.com"  # À MODIFIER
FTP_USER = "ig6i34_Yves"     # À MODIFIER
FTP_PASS = "Cf301164!000" # À MODIFIER
FTP_REMOTE_PATH = "/meteo_data.json"

# Options
DAYS_TO_FETCH = 7  # Nombre de jours à récupérer
BACKUP_ENABLED = True

# ══════════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════════

def log(message):
    """Écrit dans le fichier log avec timestamp"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    log_message = f"[{timestamp}] {message}"
    print(log_message)
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message + '\n')

# ══════════════════════════════════════════════════════════════
# RÉCUPÉRATION DEPUIS WEATHER UNDERGROUND
# ══════════════════════════════════════════════════════════════

def fetch_wunderground_data(date=None):
    """
    Récupère les données depuis Weather Underground API
    https://docs.google.com/document/d/1eKCnKXI9xnoMGRRzOL1xPCBihNV2rOet08qpE_gArAY/edit
    """
    log("🌐 Connexion à Weather Underground API...")
    
    try:
        # Paramètres de la requête
        params = {
            'stationId': WU_STATION_ID,
            'format': 'json',
            'units': 'm',  # Unités métriques
            'apiKey': WU_API_KEY,
            'numericPrecision': 'decimal'
        }
        
        if date:
            params['date'] = date
        
        log(f"   📥 Récupération des données pour {WU_STATION_ID}...")
        
        response = requests.get(WU_API_URL, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            
            if 'observations' in data and data['observations']:
                observations = data['observations']
                log(f"   ✅ {len(observations)} observations récupérées")
                return observations
            else:
                log("   ⚠️  Aucune observation dans la réponse")
                return []
        else:
            log(f"   ❌ Erreur API : {response.status_code}")
            log(f"   Réponse : {response.text[:200]}")
            return []
            
    except Exception as e:
        log(f"❌ Erreur lors de la récupération : {e}")
        return []

# ══════════════════════════════════════════════════════════════
# TRAITEMENT DES DONNÉES
# ══════════════════════════════════════════════════════════════

def process_observations(observations):
    """
    Traite les observations et les agrège par jour
    """
    log("🔢 Traitement des observations...")
    
    daily_data = {}
    
    for obs in observations:
        try:
            # Date de l'observation
            epoch = obs.get('epoch')
            if not epoch:
                continue
            
            dt = datetime.fromtimestamp(int(epoch))
            date_key = dt.strftime('%Y-%m-%d')
            
            # Extraire les données météo
            metric = obs.get('metric', {})
            
            temp = metric.get('temp')
            humidity = obs.get('humidity')
            wind_speed = metric.get('windSpeed')
            wind_gust = metric.get('windGust')
            precip_rate = metric.get('precipRate', 0)
            precip_total = metric.get('precipTotal', 0)
            pressure = metric.get('pressure')
            
            # Initialiser le jour si nécessaire
            if date_key not in daily_data:
                daily_data[date_key] = {
                    'temps': [],
                    'humidities': [],
                    'wind_speeds': [],
                    'wind_gusts': [],
                    'precip_total': 0,
                    'pressures': []
                }
            
            # Ajouter les valeurs
            if temp is not None:
                daily_data[date_key]['temps'].append(float(temp))
            if humidity is not None:
                daily_data[date_key]['humidities'].append(float(humidity))
            if wind_speed is not None:
                daily_data[date_key]['wind_speeds'].append(float(wind_speed))
            if wind_gust is not None:
                daily_data[date_key]['wind_gusts'].append(float(wind_gust))
            if precip_total is not None:
                current_precip = float(precip_total)
                if current_precip > daily_data[date_key]['precip_total']:
                    daily_data[date_key]['precip_total'] = current_precip
            if pressure is not None:
                daily_data[date_key]['pressures'].append(float(pressure))
                
        except Exception as e:
            log(f"   ⚠️  Erreur traitement observation : {e}")
            continue
    
    log(f"   ✅ {len(daily_data)} jours traités")
    return daily_data

def aggregate_daily_data(daily_data):
    """
    Agrège les données par jour (min, max, moyenne)
    """
    log("📊 Agrégation des données journalières...")
    
    result = {}
    
    for date_key, data in daily_data.items():
        try:
            result[date_key] = {
                'temp_min': min(data['temps']) if data['temps'] else 0,
                'temp_avg': sum(data['temps']) / len(data['temps']) if data['temps'] else 0,
                'temp_max': max(data['temps']) if data['temps'] else 0,
                'hum_avg': sum(data['humidities']) / len(data['humidities']) if data['humidities'] else 0,
                'wind_avg': sum(data['wind_speeds']) / len(data['wind_speeds']) if data['wind_speeds'] else 0,
                'wind_max': max(data['wind_gusts']) if data['wind_gusts'] else 0,
                'rain': data['precip_total'],
                'pressure': sum(data['pressures']) / len(data['pressures']) if data['pressures'] else 0,
            }
            
            # Arrondir à 1 décimale
            for key in result[date_key]:
                result[date_key][key] = round(result[date_key][key], 1)
                
        except Exception as e:
            log(f"   ⚠️  Erreur agrégation {date_key} : {e}")
            continue
    
    log(f"   ✅ {len(result)} jours agrégés")
    return result

# ══════════════════════════════════════════════════════════════
# GESTION DU JSON
# ══════════════════════════════════════════════════════════════

def load_existing_json():
    """Charge le JSON existant s'il existe"""
    if os.path.exists(JSON_OUTPUT):
        try:
            with open(JSON_OUTPUT, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"⚠️  Erreur lecture JSON existant : {e}")
    return {}

def merge_data(existing, new_data):
    """Fusionne les nouvelles données avec l'existant"""
    log("🔄 Fusion des données...")
    
    # Copier l'existant
    merged = existing.copy()
    
    # Ajouter/mettre à jour avec les nouvelles données
    for date_key, data in new_data.items():
        merged[date_key] = data
    
    log(f"   ✅ {len(merged)} jours au total après fusion")
    return merged

def backup_json():
    """Crée une sauvegarde du JSON existant"""
    if not os.path.exists(JSON_OUTPUT):
        return
    
    backup_name = JSON_OUTPUT.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
    
    try:
        import shutil
        shutil.copy2(JSON_OUTPUT, backup_name)
        log(f"💾 Sauvegarde créée : {os.path.basename(backup_name)}")
    except Exception as e:
        log(f"⚠️  Erreur sauvegarde : {e}")

def save_json(data):
    """Sauvegarde le JSON localement"""
    try:
        with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        
        size_kb = os.path.getsize(JSON_OUTPUT) / 1024
        log(f"💾 JSON sauvegardé : {size_kb:.1f} Ko")
        return True
        
    except Exception as e:
        log(f"❌ Erreur sauvegarde JSON : {e}")
        return False

# ══════════════════════════════════════════════════════════════
# UPLOAD FTP
# ══════════════════════════════════════════════════════════════

def upload_to_wordpress():
    """Upload le JSON sur WordPress via FTP"""
    log("📤 Upload vers WordPress...")
    
    try:
        ftp = FTP(FTP_HOST)
        ftp.login(FTP_USER, FTP_PASS)
        
        log(f"   🔐 Connecté à {FTP_HOST}")
        
        # Créer le dossier Meteo s'il n'existe pas
        remote_dir = '/'.join(FTP_REMOTE_PATH.split('/')[:-1])
        
        try:
            # Essayer de créer les dossiers parents si nécessaire
            dirs = remote_dir.split('/')
            current_path = ''
            for d in dirs:
                if not d:
                    continue
                current_path += '/' + d
                try:
                    ftp.cwd(current_path)
                except:
                    try:
                        ftp.mkd(current_path)
                        log(f"   📁 Dossier créé : {current_path}")
                        ftp.cwd(current_path)
                    except:
                        pass
        except Exception as e:
            log(f"   ⚠️  Avertissement création dossiers : {e}")
        
        # Upload du fichier
        with open(JSON_OUTPUT, 'rb') as f:
            ftp.storbinary(f'STOR {FTP_REMOTE_PATH}', f)
        
        ftp.quit()
        log("✅ Upload terminé avec succès !")
        return True
        
    except Exception as e:
        log(f"❌ Erreur upload FTP : {e}")
        return False

# ══════════════════════════════════════════════════════════════
# FONCTION PRINCIPALE
# ══════════════════════════════════════════════════════════════

def main():
    """Fonction principale d'automatisation"""
    log("=" * 70)
    log("🤖 AUTOMATISATION STATION MÉTÉO KAP SEVY - Weather Underground")
    log("=" * 70)
    
    # Étape 1 : Récupération des données
    log("\n📥 ÉTAPE 1 : Récupération depuis Weather Underground")
    
    observations = fetch_wunderground_data()
    
    if not observations:
        log("❌ Aucune donnée récupérée. Arrêt.")
        return False
    
    # Étape 2 : Traitement
    log("\n📊 ÉTAPE 2 : Traitement des données")
    
    daily_raw = process_observations(observations)
    new_data = aggregate_daily_data(daily_raw)
    
    if not new_data:
        log("❌ Aucune donnée à sauvegarder. Arrêt.")
        return False
    
    # Étape 3 : Fusion avec l'existant
    log("\n🔄 ÉTAPE 3 : Mise à jour du JSON")
    
    if BACKUP_ENABLED:
        backup_json()
    
    existing_data = load_existing_json()
    merged_data = merge_data(existing_data, new_data)
    
    if not save_json(merged_data):
        log("❌ Échec de la sauvegarde. Arrêt.")
        return False
    
    # Étape 4 : Upload vers WordPress
    log("\n🌐 ÉTAPE 4 : Upload vers WordPress")
    
    if not upload_to_wordpress():
        log("⚠️  Upload échoué, mais JSON local à jour")
    
    # Résumé final
    log("\n" + "=" * 70)
    log("✅ AUTOMATISATION TERMINÉE AVEC SUCCÈS")
    log(f"📊 {len(merged_data)} jours de données disponibles")
    log(f"🆕 {len(new_data)} jours mis à jour")
    log(f"📅 Dernière mise à jour : {datetime.now().strftime('%d/%m/%Y à %H:%M:%S')}")
    log("=" * 70)
    
    return True

# ══════════════════════════════════════════════════════════════
# EXÉCUTION
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        log(f"💥 ERREUR CRITIQUE : {e}")
        import traceback
        log(traceback.format_exc())
        sys.exit(1)