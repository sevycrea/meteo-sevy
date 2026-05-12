#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'agrégation des données horaires en 3 périodes de 8 heures
Enrichit meteo_data.json avec les moyennes par période
"""

import json
import os
import sys
from datetime import datetime, timedelta
from collections import defaultdict
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from io_helpers import atomic_write_json

# ============================================
# CONFIGURATION
# ============================================

# Chemins — relatifs à la racine du repo
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOURLY_FILE = os.path.join(BASE_DIR, "data", "meteo_data_hourly.json")
DAILY_FILE  = os.path.join(BASE_DIR, "data", "meteo_data.json")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "meteo_data_enriched.json")
LOG_FILE    = os.path.join(BASE_DIR, "logs", "aggregation.log")

# Périodes (heures de début, ne pas inclure la fin)
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

def load_hourly_data():
    """Charger les données horaires"""
    if not os.path.exists(HOURLY_FILE):
        log(f"⚠️ Fichier horaire introuvable: {HOURLY_FILE}")
        return None
    
    try:
        with open(HOURLY_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"✅ Données horaires chargées: {len(data)} entrées")
        return data
    except Exception as e:
        log(f"❌ Erreur chargement horaire: {e}")
        return None

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

def get_hour_from_timestamp(timestamp):
    """Extraire l'heure d'un timestamp"""
    try:
        # Format: "2025-08-01 14:30:00"
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        return dt.hour
    except:
        return None

def get_date_from_timestamp(timestamp):
    """Extraire la date d'un timestamp"""
    try:
        dt = datetime.strptime(timestamp, '%Y-%m-%d %H:%M:%S')
        return dt.strftime('%Y-%m-%d')
    except:
        return None

def get_period_for_hour(hour):
    """Déterminer la période pour une heure donnée"""
    # Période 1: 04h-12h
    if 4 <= hour < 12:
        return 'p1'
    # Période 2: 12h-20h
    elif 12 <= hour < 20:
        return 'p2'
    # Période 3: 20h-04h (nuit)
    else:
        return 'p3'

def aggregate_by_periods(hourly_data):
    """Agréger les données horaires par période de 8h"""
    
    # Structure: {date: {p1: {temps: [], ...}, p2: {...}, p3: {...}}}
    periods_data = defaultdict(lambda: {
        'p1': defaultdict(list),
        'p2': defaultdict(list),
        'p3': defaultdict(list)
    })
    
    for timestamp, values in hourly_data.items():
        date = get_date_from_timestamp(timestamp)
        hour = get_hour_from_timestamp(timestamp)
        
        if not date or hour is None:
            continue
        
        # Déterminer la période
        period = get_period_for_hour(hour)
        
        # Pour la période 3 (20h-04h), les heures 00h-03h appartiennent au jour précédent
        if period == 'p3' and hour < 4:
            # Cette mesure de nuit appartient au jour d'avant
            dt = datetime.strptime(date, '%Y-%m-%d')
            previous_day = (dt - timedelta(days=1)).strftime('%Y-%m-%d')
            date = previous_day
        
        # Ajouter les valeurs à la période correspondante
        period_dict = periods_data[date][period]
        
        if values.get('temp') is not None:
            period_dict['temps'].append(float(values['temp']))
        if values.get('humidity') is not None:
            period_dict['humidity'].append(float(values['humidity']))
        if values.get('pressure') is not None:
            period_dict['pressure'].append(float(values['pressure']))
        if values.get('wind_speed') is not None:
            period_dict['wind_speeds'].append(float(values['wind_speed']))
        if values.get('wind_gust') is not None:
            period_dict['wind_gusts'].append(float(values['wind_gust']))
        if values.get('rain') is not None:
            period_dict['rain_amounts'].append(float(values['rain']))
    
    return periods_data

def calculate_period_stats(period_data):
    """Calculer les statistiques pour une période"""
    stats = {}
    
    # Température
    if period_data['temps']:
        stats['temp_avg'] = round(np.mean(period_data['temps']), 1)
        stats['temp_min'] = round(np.min(period_data['temps']), 1)
        stats['temp_max'] = round(np.max(period_data['temps']), 1)
    else:
        stats['temp_avg'] = None
    
    # Humidité
    if period_data['humidity']:
        stats['hum_avg'] = round(np.mean(period_data['humidity']), 1)
    else:
        stats['hum_avg'] = None
    
    # Pression
    if period_data['pressure']:
        stats['pressure_avg'] = round(np.mean(period_data['pressure']), 1)
        stats['pressure_min'] = round(np.min(period_data['pressure']), 1)
        stats['pressure_max'] = round(np.max(period_data['pressure']), 1)
    else:
        stats['pressure_avg'] = None
    
    # Vent
    if period_data['wind_speeds']:
        stats['wind_avg'] = round(np.mean(period_data['wind_speeds']), 1)
        stats['wind_max'] = round(np.max(period_data['wind_speeds']), 1)
    else:
        stats['wind_avg'] = None
        stats['wind_max'] = None
    
    if period_data['wind_gusts']:
        stats['gust_max'] = round(np.max(period_data['wind_gusts']), 1)
    else:
        stats['gust_max'] = None
    
    # Pluie (total de la période)
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
            
            # Amplitude totale
            all_temps = [
                enriched[date]['p1_temp_min'], enriched[date]['p1_temp_max'],
                enriched[date]['p2_temp_min'], enriched[date]['p2_temp_max'],
                enriched[date]['p3_temp_min'], enriched[date]['p3_temp_max']
            ]
            enriched[date]['temp_amplitude_day'] = round(
                max(all_temps) - min(all_temps), 1
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
        
        days_enriched += 1
    
    return enriched, days_enriched

def save_enriched_data(data):
    """Sauvegarder les données enrichies (atomique)."""
    try:
        atomic_write_json(OUTPUT_FILE, data, sort_keys=True)
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
    log("📊 AGRÉGATION DES DONNÉES HORAIRES EN 3 PÉRIODES")
    log("=" * 70)
    log("Périodes:")
    log("  P1: 04h00 - 12h00 (matin)")
    log("  P2: 12h00 - 20h00 (après-midi)")
    log("  P3: 20h00 - 04h00 (nuit)")
    log("")
    
    # 1. Charger les données
    hourly_data = load_hourly_data()
    if not hourly_data:
        log("❌ Impossible de continuer sans données horaires")
        return
    
    daily_data = load_daily_data()
    if not daily_data:
        log("❌ Impossible de continuer sans données journalières")
        return
    
    # 2. Agréger par périodes
    log("🔄 Agrégation par périodes de 8h...")
    periods_data = aggregate_by_periods(hourly_data)
    log(f"   ✅ {len(periods_data)} jours avec données par période")
    
    # 3. Enrichir les données journalières
    log("📈 Enrichissement des données journalières...")
    enriched_data, days_enriched = enrich_daily_data(daily_data, periods_data)
    log(f"   ✅ {days_enriched} jours enrichis avec données périodiques")
    
    # 4. Sauvegarder
    log("💾 Sauvegarde...")
    if save_enriched_data(enriched_data):
        log("")
        log("=" * 70)
        log("✅ AGRÉGATION TERMINÉE AVEC SUCCÈS")
        log("=" * 70)
        log(f"📊 Total: {len(enriched_data)} jours")
        log(f"📊 Enrichis: {days_enriched} jours")
        log(f"📂 Fichier: {OUTPUT_FILE}")
        log("=" * 70)
    else:
        log("❌ Échec de la sauvegarde")

if __name__ == "__main__":
    main()
