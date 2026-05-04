#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de fusion des données CSV historiques
Convertit tous les CSV en JSON avec la nouvelle structure complète
"""

import json
import os
import csv
import re
from datetime import datetime
from collections import defaultdict

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
CSV_DIR = f"{BASE_DIR}/data/csv"  # Dossier contenant les CSV
JSON_OUTPUT = f"{BASE_DIR}/data/json/meteo_data.json"
BACKUP_DIR = f"{BASE_DIR}/data/json/backup"

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Afficher un message"""
    print(message)

def clean_number(value):
    """
    Nettoyer une valeur numérique :
    - Supprimer TOUS les espaces (normaux ET insécables \xa0)
    - Remplacer virgule par point
    """
    if not value or value == '' or value == '-':
        return None
    try:
        # Supprimer tous les whitespace (espaces, \xa0, etc.)
        clean = re.sub(r'\s+', '', value)
        # Remplacer virgule par point
        clean = clean.replace(',', '.')
        return float(clean)
    except:
        return None

def backup_current_json():
    """Sauvegarder le JSON actuel avant fusion"""
    if not os.path.exists(JSON_OUTPUT):
        log("ℹ️  Pas de JSON existant à sauvegarder")
        return
    
    os.makedirs(BACKUP_DIR, exist_ok=True)
    backup_name = f"meteo_data_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    backup_path = os.path.join(BACKUP_DIR, backup_name)
    
    try:
        import shutil
        shutil.copy2(JSON_OUTPUT, backup_path)
        log(f"💾 Backup créé : {backup_name}")
    except Exception as e:
        log(f"⚠️  Erreur backup : {e}")

def load_existing_json():
    """Charger le JSON existant"""
    if os.path.exists(JSON_OUTPUT):
        try:
            with open(JSON_OUTPUT, 'r', encoding='utf-8') as f:
                data = json.load(f)
            log(f"📂 JSON existant chargé : {len(data)} jours")
            return data
        except Exception as e:
            log(f"⚠️  Erreur lecture JSON : {e}")
    return {}

def find_csv_files():
    """Trouver tous les fichiers CSV dans le dossier"""
    if not os.path.exists(CSV_DIR):
        log(f"❌ Dossier CSV introuvable : {CSV_DIR}")
        return []
    
    csv_files = []
    for filename in os.listdir(CSV_DIR):
        if filename.endswith('.csv'):
            csv_files.append(os.path.join(CSV_DIR, filename))
    
    csv_files.sort()  # Trier par ordre alphabétique
    log(f"📁 {len(csv_files)} fichiers CSV trouvés")
    return csv_files

def parse_csv_observations(csv_file):
    """
    Parser un fichier CSV et agréger par jour
    
    Format CSV Weathercloud (français, séparateur ;):
    Date (Europe/Zurich);Température intérieur (°C);Température (°C);...
    """
    
    log(f"   📄 Traitement : {os.path.basename(csv_file)}")
    
    # Détecter l'encodage du fichier
    encodings = ['utf-16-le', 'utf-16-be', 'utf-16', 'utf-8', 'latin-1', 'iso-8859-1', 'cp1252']
    csv_content = None
    encoding_used = None
    
    for encoding in encodings:
        try:
            with open(csv_file, 'r', encoding=encoding) as f:
                csv_content = f.read()
                encoding_used = encoding
                break
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    if csv_content is None:
        log(f"      ❌ Impossible de décoder le fichier")
        return {}
    
    log(f"      ℹ️  Encodage détecté : {encoding_used}")
    
    # Données agrégées par jour
    daily_data = defaultdict(lambda: {
        'temps': [],
        'humidity': [],
        'wind_speeds': [],
        'wind_gusts': [],
        'pressures': [],
        'precip_accum': []
    })
    
    try:
        # Parser le CSV depuis le contenu (séparateur point-virgule)
        import io
        csv_reader = csv.DictReader(io.StringIO(csv_content), delimiter=';')
        
        rows_processed = 0
        rows_with_data = 0
        
        for row in csv_reader:
            try:
                rows_processed += 1
                
                # Parser la date/heure (format DD/MM/YYYY HH:MM:SS)
                time_str = row.get('Date (Europe/Zurich)', '').strip()
                if not time_str or time_str == '':
                    continue
                
                # Format: "01/08/2025 00:00:00"
                try:
                    dt = datetime.strptime(time_str, '%d/%m/%Y %H:%M:%S')
                except ValueError:
                    continue
                
                date_key = dt.strftime('%Y-%m-%d')
                
                # Température (chercher la colonne exacte)
                temp = row.get('Température (°C)', '').strip()
                if not temp:
                    # Essayer avec d'autres variantes
                    for col_name in row.keys():
                        if col_name.startswith('Temp') and 'int' not in col_name and '°C' in col_name:
                            temp = row[col_name].strip()
                            break
                
                temp_value = clean_number(temp)
                if temp_value is not None:
                    daily_data[date_key]['temps'].append(temp_value)
                    rows_with_data += 1
                
                # Humidité
                hum = row.get('Humidité (%)', '').strip()
                if not hum:
                    for col_name in row.keys():
                        if col_name.startswith('Humidit') and 'int' not in col_name and '%' in col_name:
                            hum = row[col_name].strip()
                            break
                
                hum_value = clean_number(hum)
                if hum_value is not None:
                    daily_data[date_key]['humidity'].append(hum_value)
                
                # Vitesse moyenne du vent
                wind = None
                for col_name in row.keys():
                    if 'Vitesse moyenne' in col_name or 'vitesse moyenne' in col_name:
                        wind = row[col_name].strip()
                        break
                
                wind_value = clean_number(wind)
                if wind_value is not None:
                    daily_data[date_key]['wind_speeds'].append(wind_value)
                
                # Rafales de vent
                gust = None
                for col_name in row.keys():
                    if 'Rafale' in col_name or 'rafale' in col_name:
                        gust = row[col_name].strip()
                        break
                
                gust_value = clean_number(gust)
                if gust_value is not None:
                    daily_data[date_key]['wind_gusts'].append(gust_value)
                
                # Pression
                pressure = None
                for col_name in row.keys():
                    if 'Pression' in col_name or 'pression' in col_name:
                        pressure = row[col_name].strip()
                        break
                
                pressure_value = clean_number(pressure)
                if pressure_value is not None:
                    daily_data[date_key]['pressures'].append(pressure_value)
                
                # Pluie cumulée
                rain = None
                for col_name in row.keys():
                    if 'Pluie' in col_name and 'Intensit' not in col_name:
                        rain = row[col_name].strip()
                        break
                
                rain_value = clean_number(rain)
                if rain_value is not None:
                    daily_data[date_key]['precip_accum'].append(rain_value)
            
            except Exception as e:
                continue  # Ignorer les lignes avec erreurs
        
        log(f"      ℹ️  {rows_processed} lignes traitées, {rows_with_data} avec données")
        log(f"      ✅ {len(daily_data)} jours extraits")
        return daily_data
        
    except Exception as e:
        log(f"      ❌ Erreur lecture CSV : {e}")
        import traceback
        traceback.print_exc()
        return {}

def aggregate_daily_data(daily_data):
    """
    Agréger les observations en statistiques journalières
    """
    
    result = {}
    
    for date_key, data in daily_data.items():
        try:
            # Température (min, avg, max)
            if data['temps']:
                temp_min = min(data['temps'])
                temp_avg = sum(data['temps']) / len(data['temps'])
                temp_max = max(data['temps'])
            else:
                temp_min = temp_avg = temp_max = 0
            
            # Humidité (min, avg, max)
            if data['humidity']:
                hum_min = min(data['humidity'])
                hum_avg = sum(data['humidity']) / len(data['humidity'])
                hum_max = max(data['humidity'])
            else:
                hum_min = hum_avg = hum_max = 0
            
            # Vent (min, avg, max)
            if data['wind_speeds']:
                wind_min = min(data['wind_speeds'])
                wind_avg = sum(data['wind_speeds']) / len(data['wind_speeds'])
                wind_max = max(data['wind_speeds'])
            else:
                wind_min = wind_avg = wind_max = 0
            
            # Rafales max
            if data['wind_gusts']:
                gust_max = max(data['wind_gusts'])
            else:
                gust_max = wind_max
            
            # Pression (min, avg, max)
            if data['pressures']:
                pressure_min = min(data['pressures'])
                pressure_avg = sum(data['pressures']) / len(data['pressures'])
                pressure_max = max(data['pressures'])
            else:
                pressure_min = pressure_avg = pressure_max = 0
            
            # Pluie (total du jour = max de precip_accum)
            if data['precip_accum']:
                rain = max(data['precip_accum'])
            else:
                rain = 0
            
            result[date_key] = {
                'temp_min': round(temp_min, 1),
                'temp_avg': round(temp_avg, 1),
                'temp_max': round(temp_max, 1),
                'hum_min': round(hum_min, 1),
                'hum_avg': round(hum_avg, 1),
                'hum_max': round(hum_max, 1),
                'wind_min': round(wind_min, 1),
                'wind_avg': round(wind_avg, 1),
                'wind_max': round(wind_max, 1),
                'gust_max': round(gust_max, 1),
                'rain': round(rain, 1),
                'pressure_min': round(pressure_min, 1),
                'pressure_avg': round(pressure_avg, 1),
                'pressure_max': round(pressure_max, 1),
            }
            
        except Exception as e:
            log(f"      ⚠️  Erreur agrégation {date_key} : {e}")
            continue
    
    return result

def merge_data(existing, csv_data):
    """
    Fusionner les données CSV avec le JSON existant
    Les données CSV écrasent les anciennes (si même date)
    """
    
    merged = existing.copy()
    
    for date_key, data in csv_data.items():
        merged[date_key] = data
    
    return merged

def save_json(data):
    """Sauvegarder le JSON fusionné"""
    try:
        with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        
        log(f"✅ JSON sauvegardé : {len(data)} jours")
        log(f"📂 Fichier : {JSON_OUTPUT}")
        
    except Exception as e:
        log(f"❌ Erreur sauvegarde JSON : {e}")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🔄 FUSION DES DONNÉES CSV HISTORIQUES")
    log("=" * 70)
    
    # 1. Backup du JSON actuel
    log("\n📦 ÉTAPE 1 : Sauvegarde du JSON actuel")
    backup_current_json()
    
    # 2. Charger le JSON existant
    log("\n📂 ÉTAPE 2 : Chargement du JSON existant")
    existing_data = load_existing_json()
    
    # 3. Trouver les CSV
    log("\n🔍 ÉTAPE 3 : Recherche des fichiers CSV")
    csv_files = find_csv_files()
    
    if not csv_files:
        log("❌ Aucun fichier CSV trouvé !")
        log(f"   Vérifiez que le dossier {CSV_DIR} contient des fichiers .csv")
        return
    
    # 4. Parser tous les CSV
    log("\n📊 ÉTAPE 4 : Traitement des CSV")
    all_csv_data = {}
    
    for csv_file in csv_files:
        daily_data = parse_csv_observations(csv_file)
        aggregated = aggregate_daily_data(daily_data)
        
        # Fusionner avec les données déjà parsées
        for date_key, data in aggregated.items():
            all_csv_data[date_key] = data
    
    log(f"\n   ✅ Total : {len(all_csv_data)} jours extraits des CSV")
    
    # 5. Fusionner avec le JSON existant
    log("\n🔀 ÉTAPE 5 : Fusion des données")
    merged_data = merge_data(existing_data, all_csv_data)
    
    log(f"   📊 Données existantes : {len(existing_data)} jours")
    log(f"   📊 Données CSV : {len(all_csv_data)} jours")
    log(f"   ✅ Total après fusion : {len(merged_data)} jours")
    
    # 6. Sauvegarder
    log("\n💾 ÉTAPE 6 : Sauvegarde du JSON fusionné")
    save_json(merged_data)
    
    # 7. Statistiques
    log("\n" + "=" * 70)
    log("✅ FUSION TERMINÉE AVEC SUCCÈS")
    log("=" * 70)
    
    dates = sorted(merged_data.keys())
    if dates:
        log(f"📅 Première date : {dates[0]}")
        log(f"📅 Dernière date : {dates[-1]}")
        log(f"📊 Total : {len(dates)} jours de données")
    
    log("\n💡 Prochaines étapes :")
    log("   1. Vérifiez le fichier JSON")
    log("   2. Ré-entraînez le modèle IA : python3 train_model.py")
    log("   3. Générez de nouvelles prévisions : python3 predict_weather.py")
    log("=" * 70)

if __name__ == "__main__":
    main()
