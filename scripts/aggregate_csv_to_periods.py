#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'agrégation des CSV Weathercloud en 3 périodes de 8 heures
Lit tous les CSV historiques et crée meteo_data_enriched.json
"""

import json
import os
import csv
import io
import re
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
CSV_DIR = f"{BASE_DIR}/data/csv"
DAILY_FILE = f"{BASE_DIR}/data/json/meteo_data.json"
OUTPUT_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
LOG_FILE = f"{BASE_DIR}/logs/aggregation_csv.log"

# Périodes
PERIODS = {
    'p1': (4, 12),   # 04:00 - 11:59
    'p2': (12, 20),  # 12:00 - 19:59
    'p3': (20, 28)   # 20:00 - 03:59 (28 = 4h le lendemain)
}

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Écrire dans le fichier log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message)

def clean_number(value):
    """
    Nettoyer une valeur numérique
    Gère les espaces insécables (\xa0), virgules, etc.
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

def detect_encoding(filepath):
    """Détecter l'encodage d'un fichier CSV"""
    encodings = ['utf-16-le', 'utf-16-be', 'utf-8', 'latin-1', 'cp1252']
    
    for encoding in encodings:
        try:
            with open(filepath, 'r', encoding=encoding) as f:
                f.read(100)
            return encoding
        except:
            continue
    
    return 'utf-8'

def load_daily_data():
    """Charger les données journalières existantes"""
    try:
        with open(DAILY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"✅ Données journalières chargées: {len(data)} jours")
        return data
    except Exception as e:
        log(f"❌ Erreur chargement journalier: {e}")
        return {}

def get_period_for_hour(hour):
    """Déterminer la période pour une heure donnée"""
    if 4 <= hour < 12:
        return 'p1'
    elif 12 <= hour < 20:
        return 'p2'
    else:
        return 'p3'

def parse_csv_files():
    """Parser tous les fichiers CSV et extraire les données horaires par période"""
    
    # Structure: {date: {p1: {temps: [], ...}, p2: {...}, p3: {...}}}
    periods_data = defaultdict(lambda: {
        'p1': defaultdict(list),
        'p2': defaultdict(list),
        'p3': defaultdict(list)
    })
    
    # Lister tous les CSV
    csv_files = [f for f in os.listdir(CSV_DIR) if f.endswith('.csv')]
    csv_files.sort()
    
    log(f"📂 {len(csv_files)} fichiers CSV trouvés")
    
    total_rows = 0
    
    for csv_file in csv_files:
        filepath = os.path.join(CSV_DIR, csv_file)
        
        try:
            # Détecter l'encodage
            encoding = detect_encoding(filepath)
            
            # Lire le fichier
            with open(filepath, 'r', encoding=encoding) as f:
                content = f.read()
            
            # Parser le CSV
            reader = csv.DictReader(io.StringIO(content), delimiter=';')
            
            rows_in_file = 0
            
            for row in reader:
                # Date et heure
                date_str = row.get('Date (Europe/Zurich)', '').strip()
                if not date_str:
                    continue
                
                try:
                    # Format: "01/08/2025 00:00:00"
                    dt = datetime.strptime(date_str, '%d/%m/%Y %H:%M:%S')
                    date = dt.strftime('%Y-%m-%d')
                    hour = dt.hour
                except:
                    continue
                
                # Déterminer la période
                period = get_period_for_hour(hour)
                
                # Pour la période 3 (20h-04h), les heures 00h-03h appartiennent au jour précédent
                if period == 'p3' and hour < 4:
                    previous_day = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
                    date = previous_day
                
                # Extraire les valeurs
                period_dict = periods_data[date][period]
                
                # Température
                temp = None
                for col_name in row.keys():
                    if 'Temp' in col_name and 'int' not in col_name and '°C' in col_name:
                        temp = clean_number(row[col_name])
                        break
                if temp is not None:
                    period_dict['temps'].append(temp)
                
                # Humidité
                hum = None
                for col_name in row.keys():
                    if 'Humidit' in col_name and '%' in col_name:
                        hum = clean_number(row[col_name])
                        break
                if hum is not None:
                    period_dict['humidity'].append(hum)
                
                # Pression
                pressure = None
                for col_name in row.keys():
                    if 'Pression' in col_name:
                        pressure = clean_number(row[col_name])
                        break
                if pressure is not None:
                    period_dict['pressure'].append(pressure)
                
                # Vent moyen
                wind = None
                for col_name in row.keys():
                    if 'Vitesse moyenne' in col_name or 'vitesse moyenne' in col_name:
                        wind = clean_number(row[col_name])
                        break
                if wind is not None:
                    period_dict['wind_speeds'].append(wind)
                
                # Rafales
                gust = None
                for col_name in row.keys():
                    if 'Rafale' in col_name or 'rafale' in col_name:
                        gust = clean_number(row[col_name])
                        break
                if gust is not None:
                    period_dict['wind_gusts'].append(gust)
                
                # Pluie
                rain = None
                for col_name in row.keys():
                    if 'Pluie' in col_name and 'Intensit' not in col_name:
                        rain = clean_number(row[col_name])
                        break
                if rain is not None:
                    period_dict['rain_amounts'].append(rain)
                
                rows_in_file += 1
            
            total_rows += rows_in_file
            log(f"   ✅ {csv_file}: {rows_in_file} lignes")
            
        except Exception as e:
            log(f"   ❌ Erreur {csv_file}: {e}")
    
    log(f"📊 Total: {total_rows} lignes parsées")
    log(f"📊 {len(periods_data)} jours avec données")
    
    return periods_data

def calculate_period_stats(period_data):
    """Calculer les statistiques pour une période"""
    stats = {}
    
    # Température
    if period_data['temps']:
        stats['temp_avg'] = round(np.mean(period_data['temps']), 1)
        stats['temp_min'] = round(np.min(period_data['temps']), 1)
        stats['temp_max'] = round(np.max(period_data['temps']), 1)
        stats['temp_range'] = round(stats['temp_max'] - stats['temp_min'], 1)
    else:
        stats['temp_avg'] = None
        stats['temp_min'] = None
        stats['temp_max'] = None
        stats['temp_range'] = None
    
    # Humidité
    if period_data['humidity']:
        stats['hum_avg'] = round(np.mean(period_data['humidity']), 1)
        stats['hum_min'] = round(np.min(period_data['humidity']), 1)
        stats['hum_max'] = round(np.max(period_data['humidity']), 1)
        stats['hum_range'] = round(stats['hum_max'] - stats['hum_min'], 1)
    else:
        stats['hum_avg'] = None
        stats['hum_min'] = None
        stats['hum_max'] = None
        stats['hum_range'] = None
    
    # Pression
    if period_data['pressure']:
        stats['pressure_avg'] = round(np.mean(period_data['pressure']), 1)
        stats['pressure_min'] = round(np.min(period_data['pressure']), 1)
        stats['pressure_max'] = round(np.max(period_data['pressure']), 1)
        stats['pressure_range'] = round(stats['pressure_max'] - stats['pressure_min'], 1)
    else:
        stats['pressure_avg'] = None
        stats['pressure_min'] = None
        stats['pressure_max'] = None
        stats['pressure_range'] = None
    
    # Vent
    if period_data['wind_speeds']:
        stats['wind_avg'] = round(np.mean(period_data['wind_speeds']), 1)
        stats['wind_max'] = round(np.max(period_data['wind_speeds']), 1)
        stats['wind_min'] = round(np.min(period_data['wind_speeds']), 1)
        stats['wind_range'] = round(stats['wind_max'] - stats['wind_min'], 1)
    else:
        stats['wind_avg'] = None
        stats['wind_max'] = None
        stats['wind_min'] = None
        stats['wind_range'] = None
    
    if period_data['wind_gusts']:
        stats['gust_max'] = round(np.max(period_data['wind_gusts']), 1)
    else:
        stats['gust_max'] = None
    
    # Pluie
    if period_data['rain_amounts']:
        total_rain = sum(period_data['rain_amounts'])
        stats['rain'] = round(total_rain, 1)
        stats['has_rain'] = total_rain > 0.1
    else:
        stats['rain'] = 0.0
        stats['has_rain'] = False
    
    return stats

def enrich_daily_data(daily_data, periods_data):
    """Enrichir les données journalières avec les statistiques par période"""
    
    enriched = daily_data.copy()
    days_enriched = 0
    
    for date, periods in periods_data.items():
        if date not in enriched:
            # Si la date n'existe pas dans les données journalières, on l'ignore
            continue
        
        # Vérifier qu'on a assez de données pour les 3 périodes
        has_enough_data = True
        for period_name in ['p1', 'p2', 'p3']:
            if not periods[period_name]['temps']:
                has_enough_data = False
                break
        
        if not has_enough_data:
            continue
        
        # Ajouter les stats pour chaque période
        for period_name, period_data in periods.items():
            stats = calculate_period_stats(period_data)
            
            # Préfixer avec le nom de la période
            for key, value in stats.items():
                enriched[date][f'{period_name}_{key}'] = value
        
        # Calculer des features dérivées
        if all(f'p{i}_temp_avg' in enriched[date] and enriched[date][f'p{i}_temp_avg'] is not None 
               for i in [1, 2, 3]):
            # Variation de température entre périodes
            enriched[date]['temp_p1_to_p2'] = round(
                enriched[date]['p2_temp_avg'] - enriched[date]['p1_temp_avg'], 1
            )
            enriched[date]['temp_p2_to_p3'] = round(
                enriched[date]['p3_temp_avg'] - enriched[date]['p2_temp_avg'], 1
            )
            
            # Amplitude totale du jour (utilise les vrais min/max de chaque période)
            all_temps = [
                enriched[date]['p1_temp_min'], enriched[date]['p1_temp_max'],
                enriched[date]['p2_temp_min'], enriched[date]['p2_temp_max'],
                enriched[date]['p3_temp_min'], enriched[date]['p3_temp_max']
            ]
            enriched[date]['temp_amplitude_day'] = round(
                max(all_temps) - min(all_temps), 1
            )
            
            # Température max absolue du jour (LE VRAI PIC)
            enriched[date]['temp_max_day'] = round(max(all_temps), 1)
            
            # Température min absolue du jour
            enriched[date]['temp_min_day'] = round(min(all_temps), 1)
            
            # Somme des amplitudes par période (indicateur de stabilité)
            enriched[date]['temp_total_range'] = round(
                enriched[date]['p1_temp_range'] + 
                enriched[date]['p2_temp_range'] + 
                enriched[date]['p3_temp_range'], 1
            )
        
        if all(f'p{i}_pressure_avg' in enriched[date] and enriched[date][f'p{i}_pressure_avg'] is not None 
               for i in [1, 2, 3]):
            # Chute de pression maximale (indicateur d'instabilité)
            all_pressures = [
                enriched[date]['p1_pressure_min'], enriched[date]['p1_pressure_max'],
                enriched[date]['p2_pressure_min'], enriched[date]['p2_pressure_max'],
                enriched[date]['p3_pressure_min'], enriched[date]['p3_pressure_max']
            ]
            enriched[date]['pressure_drop_max'] = round(
                max(all_pressures) - min(all_pressures), 1
            )
            
            # Tendance pression sur la journée
            enriched[date]['pressure_trend_day'] = round(
                enriched[date]['p3_pressure_avg'] - enriched[date]['p1_pressure_avg'], 1
            )
            
            # Somme des variations de pression (instabilité)
            enriched[date]['pressure_total_range'] = round(
                enriched[date]['p1_pressure_range'] + 
                enriched[date]['p2_pressure_range'] + 
                enriched[date]['p3_pressure_range'], 1
            )
        
        # Features humidité
        if all(f'p{i}_hum_avg' in enriched[date] and enriched[date][f'p{i}_hum_avg'] is not None 
               for i in [1, 2, 3]):
            # Variation humidité (indicateur de temps changeant)
            all_hums = [
                enriched[date]['p1_hum_min'], enriched[date]['p1_hum_max'],
                enriched[date]['p2_hum_min'], enriched[date]['p2_hum_max'],
                enriched[date]['p3_hum_min'], enriched[date]['p3_hum_max']
            ]
            enriched[date]['hum_range_day'] = round(
                max(all_hums) - min(all_hums), 1
            )
        
        days_enriched += 1
    
    return enriched, days_enriched

def save_enriched_data(data):
    """Sauvegarder les données enrichies"""
    try:
        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
        log(f"✅ Données enrichies sauvegardées: {OUTPUT_FILE}")
        return True
    except Exception as e:
        log(f"❌ Erreur sauvegarde: {e}")
        return False

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("📊 AGRÉGATION DES CSV WEATHERCLOUD EN 3 PÉRIODES")
    log("=" * 70)
    log("Périodes:")
    log("  P1: 04h00 - 12h00 (matin)")
    log("  P2: 12h00 - 20h00 (après-midi)")
    log("  P3: 20h00 - 04h00 (nuit)")
    log("")
    
    # 1. Charger les données journalières
    daily_data = load_daily_data()
    if not daily_data:
        log("❌ Impossible de continuer sans données journalières")
        return
    
    # 2. Parser tous les CSV
    log("🔄 Lecture et parsing des fichiers CSV...")
    periods_data = parse_csv_files()
    
    if not periods_data:
        log("❌ Aucune donnée extraite des CSV")
        return
    
    # 3. Enrichir les données journalières
    log("\n📈 Enrichissement des données journalières...")
    enriched_data, days_enriched = enrich_daily_data(daily_data, periods_data)
    log(f"   ✅ {days_enriched} jours enrichis avec données périodiques")
    
    # 4. Sauvegarder
    log("\n💾 Sauvegarde...")
    if save_enriched_data(enriched_data):
        log("")
        log("=" * 70)
        log("✅ AGRÉGATION TERMINÉE AVEC SUCCÈS")
        log("=" * 70)
        log(f"📊 Total: {len(enriched_data)} jours dans le fichier")
        log(f"📊 Enrichis: {days_enriched} jours avec périodes 3x8h")
        log(f"📂 Fichier: {OUTPUT_FILE}")
        log("=" * 70)
    else:
        log("❌ Échec de la sauvegarde")

if __name__ == "__main__":
    main()
