#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prédiction avec MODÈLE ENSEMBLISTE
Utilise RF + XGBoost + LightGBM avec moyenne pondérée
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
import joblib
import math

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_FILE = f"{BASE_DIR}/data/json/predictions.json"

LATITUDE = 47.09  # Vinelz, Canton de Berne, Suisse
LONGITUDE = 7.12

# ============================================
# FONCTIONS ASTRON (copie du train)
# ============================================

def get_day_length(date_obj, latitude):
    day_of_year = date_obj.timetuple().tm_yday
    declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
    lat_rad = math.radians(latitude)
    decl_rad = math.radians(declination)
    try:
        cos_hour_angle = -math.tan(lat_rad) * math.tan(decl_rad)
        cos_hour_angle = max(-1, min(1, cos_hour_angle))
        hour_angle = math.degrees(math.acos(cos_hour_angle))
        day_length = 2 * hour_angle / 15
    except:
        day_length = 12
    return day_length

def get_solar_elevation(date_obj, latitude):
    day_of_year = date_obj.timetuple().tm_yday
    declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
    elevation = 90 - latitude + declination
    return elevation

def get_season(month, day):
    if month in [12, 1, 2]:
        return 0
    elif month in [3, 4, 5]:
        return 1
    elif month in [6, 7, 8]:
        return 2
    else:
        return 3

def get_season_progress(month, day):
    season_starts = {12: 0, 1: 31, 2: 59, 3: 0, 4: 31, 5: 61, 6: 0, 7: 30, 8: 61, 9: 0, 10: 30, 11: 61}
    if month in [12, 1, 2]:
        days_in_season = 90
        day_in_season = (0 if month == 12 else 31 if month == 1 else 62) + day - 1
    elif month in [3, 4, 5]:
        days_in_season = 92
        day_in_season = season_starts[month] + day - 1
    elif month in [6, 7, 8]:
        days_in_season = 92
        day_in_season = season_starts[month] + day - 1
    else:
        days_in_season = 91
        day_in_season = season_starts[month] + day - 1
    return day_in_season / days_in_season

def calculate_rolling_seasonal_stats(data, dates, target_idx, window=30):
    if target_idx < window:
        return None
    target_date = dates[target_idx]
    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
    target_season = get_season(target_dt.month, target_dt.day)
    same_season_temps = []
    same_season_pressures = []
    for i in range(max(0, target_idx - 60), target_idx):
        date_str = dates[i]
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        if get_season(date_obj.month, date_obj.day) == target_season:
            day_data = data[date_str]
            if 'temp_avg' in day_data:
                same_season_temps.append(day_data['temp_avg'])
            if 'pressure_avg' in day_data:
                same_season_pressures.append(day_data['pressure_avg'])
    if len(same_season_temps) < 5:
        return None
    return {
        'temp_mean': np.mean(same_season_temps[-window:]),
        'temp_std': np.std(same_season_temps[-window:]),
        'temp_trend': same_season_temps[-1] - np.mean(same_season_temps[-window:]) if len(same_season_temps) >= window else 0,
        'pressure_mean': np.mean(same_season_pressures[-window:]) if same_season_pressures else 1013.0
    }

# ============================================
# FONCTIONS PRINCIPALES
# ============================================

def load_data():
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    print(f"✅ Données chargées: {len(data)} jours")
    return data

def load_models():
    try:
        rf_temp = joblib.load(f"{MODEL_DIR}/ensemble_rf_temp.pkl")
        rf_rain = joblib.load(f"{MODEL_DIR}/ensemble_rf_rain.pkl")
        lgb_temp = joblib.load(f"{MODEL_DIR}/ensemble_lgb_temp.pkl")
        lgb_rain = joblib.load(f"{MODEL_DIR}/ensemble_lgb_rain.pkl")
        seasonal_normals = joblib.load(f"{MODEL_DIR}/ensemble_seasonal_normals.pkl")
        weights = joblib.load(f"{MODEL_DIR}/ensemble_weights.pkl")
        
        with open(f"{MODEL_DIR}/metrics_ensemble.json", 'r') as f:
            metrics = json.load(f)
        
        print(f"✅ Modèles ensemble chargés")
        print(f"   MAE: {metrics['temp_mae_ensemble']:.2f}°C")
        print(f"   Poids: RF={weights['rf']:.2f}, LGB={weights['lgb']:.2f}")
        
        return {
            'rf_temp': rf_temp, 'rf_rain': rf_rain,
            'lgb_temp': lgb_temp, 'lgb_rain': lgb_rain,
            'seasonal_normals': seasonal_normals,
            'weights': weights,
            'metrics': metrics
        }
    except Exception as e:
        print(f"❌ Erreur chargement modèles: {e}")
        return None

def prepare_features_for_prediction(data, dates, today_idx, horizon, seasonal_normals):
    """Fonction identique au train (code copié pour économiser espace)"""
    target_idx = today_idx + horizon
    reference_idx = target_idx - horizon
    
    if reference_idx < 7 or target_idx >= len(dates):
        return None
    
    target_date = dates[target_idx]
    features = []
    
    # [Code identique au train_model_ensemble prepare_features]
    # Copié ici de façon simplifiée pour gagner de l'espace
    
    for j in range(1, 8):
        past_idx = reference_idx - j
        if past_idx < 0:
            return None
        past_date = dates[past_idx]
        day_data = data[past_date]
        features.extend([
            day_data.get('temp_avg', 15),
            day_data.get('hum_avg', 70),
            day_data.get('pressure_avg', 1013),
            1 if day_data.get('rain', 0) > 0.5 else 0
        ])
        for period in ['p1', 'p2', 'p3']:
            features.extend([
                day_data.get(f'{period}_temp_avg', day_data.get('temp_avg', 15)),
                day_data.get(f'{period}_temp_min', day_data.get('temp_min', 10)),
                day_data.get(f'{period}_temp_max', day_data.get('temp_max', 20)),
                day_data.get(f'{period}_temp_range', 5),
                day_data.get(f'{period}_pressure_avg', day_data.get('pressure_avg', 1013)),
                day_data.get(f'{period}_pressure_range', 5),
                day_data.get(f'{period}_hum_avg', day_data.get('hum_avg', 70)),
                day_data.get(f'{period}_hum_range', 10),
                day_data.get(f'{period}_wind_max', 10),
                day_data.get(f'{period}_wind_range', 5),
                1 if day_data.get(f'{period}_has_rain', False) else 0
            ])
    
    yesterday_idx = reference_idx - 1
    if yesterday_idx < 0:
        return None
    yesterday = dates[yesterday_idx]
    yesterday_data = data[yesterday]
    
    features.extend([
        yesterday_data.get('temp_amplitude_day', 10),
        yesterday_data.get('pressure_drop_max', 5),
        yesterday_data.get('temp_p1_to_p2', 3),
        yesterday_data.get('temp_p2_to_p3', -2),
        yesterday_data.get('gust_max', 0),
        yesterday_data.get('temp_max_day', 20),
        yesterday_data.get('temp_min_day', 10),
        yesterday_data.get('temp_total_range', 10),
        yesterday_data.get('pressure_trend_day', 0),
        yesterday_data.get('pressure_total_range', 10),
        yesterday_data.get('hum_range_day', 20)
    ])
    
    target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
    day_of_year = target_datetime.timetuple().tm_yday
    month = target_datetime.month
    
    features.extend([day_of_year, month, horizon])
    
    temps_7d = [data[dates[reference_idx - j]].get('temp_avg', 15) for j in range(1, min(8, reference_idx + 1))]
    pressure_7d = [data[dates[reference_idx - j]].get('pressure_avg', 1013) for j in range(1, min(8, reference_idx + 1))]
    
    if len(temps_7d) >= 7:
        features.append(np.mean(temps_7d[:3]) - np.mean(temps_7d))
        features.append(pressure_7d[0] - pressure_7d[-1])
    else:
        features.extend([0, 0])
    
    # Features saisonnières
    day_of_year_rad = 2 * math.pi * day_of_year / 365.25
    features.extend([math.sin(day_of_year_rad), math.cos(day_of_year_rad)])
    
    season = get_season(month, target_datetime.day)
    season_progress = get_season_progress(month, target_datetime.day)
    features.extend([season, season_progress])
    
    day_length = get_day_length(target_datetime, LATITUDE)
    solar_elevation = get_solar_elevation(target_datetime, LATITUDE)
    features.extend([day_length, solar_elevation])
    
    if target_idx > 0:
        prev_date = datetime.strptime(dates[target_idx - 1], '%Y-%m-%d')
        prev_day_length = get_day_length(prev_date, LATITUDE)
        day_length_change = day_length - prev_day_length
    else:
        day_length_change = 0
    features.append(day_length_change)
    
    if seasonal_normals and season in seasonal_normals:
        normal_temp = seasonal_normals[season]['temp']
        normal_pressure = seasonal_normals[season]['pressure']
        normal_std = seasonal_normals[season]['temp_std']
        recent_temp = yesterday_data.get('temp_avg', 15)
        temp_anomaly = recent_temp - normal_temp
        features.append(temp_anomaly)
        features.append(temp_anomaly / normal_std if normal_std > 0 else 0)
        recent_pressure = yesterday_data.get('pressure_avg', 1013)
        pressure_anomaly = recent_pressure - normal_pressure
        features.append(pressure_anomaly)
    else:
        features.extend([0, 0, 0])
    
    seasonal_stats = calculate_rolling_seasonal_stats(data, dates, reference_idx, window=30)
    if seasonal_stats:
        features.extend([seasonal_stats['temp_mean'], seasonal_stats['temp_std'], seasonal_stats['temp_trend'], seasonal_stats['pressure_mean']])
    else:
        features.extend([15.0, 5.0, 0.0, 1013.0])
    
    is_season_transition = (season_progress < 0.15 or season_progress > 0.85)
    features.append(1 if is_season_transition else 0)
    
    month_rad = 2 * math.pi * month / 12
    features.extend([math.sin(month_rad), math.cos(month_rad)])
    
    return features

def predict_ensemble(data, dates, models):
    """Générer prédictions avec ensemble"""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    if today_str in dates:
        today_idx = dates.index(today_str)
    else:
        today_idx = len(dates) - 1
    
    forecasts = []
    
    for horizon in [0, 1, 2]:
        features = prepare_features_for_prediction(data, dates, today_idx, horizon, models['seasonal_normals'])
        
        if features is None:
            continue
        
        X = np.array([features])
        
        # Prédictions des 2 modèles
        rf_temp = models['rf_temp'].predict(X)[0]
        lgb_temp = models['lgb_temp'].predict(X)[0]
        
        # Moyenne pondérée
        weights = models['weights']
        temp_pred = (
            weights['rf'] * rf_temp +
            weights['lgb'] * lgb_temp
        )
        
        # Pluie : probabilités
        rf_rain_prob = models['rf_rain'].predict_proba(X)[0][1]
        lgb_rain_prob = models['lgb_rain'].predict_proba(X)[0][1]
        
        rain_proba = (
            weights['rf'] * rf_rain_prob +
            weights['lgb'] * lgb_rain_prob
        )
        
        pred_date = (datetime.strptime(dates[today_idx], '%Y-%m-%d') + timedelta(days=horizon)).strftime('%Y-%m-%d')
        pred_datetime = datetime.strptime(pred_date, '%Y-%m-%d')
        
        confidence = max(50, 95 - horizon * 12)
        uncertainty = 0.5 + horizon * 0.3
        
        p1_temp = temp_pred - 3
        p2_temp = temp_pred + 5
        p3_temp = temp_pred - 2
        
        forecast = {
            'date': pred_date,
            'day_name': pred_datetime.strftime('%A'),
            'day_number': int(horizon),
            'day_label': ['Aujourd\'hui', 'Demain', 'Après-demain'][horizon],
            'temperature': {
                'predicted': round(float(temp_pred), 1),
                'min_estimate': round(float(temp_pred - uncertainty), 1),
                'max_estimate': round(float(temp_pred + uncertainty), 1),
                'ensemble_detail': {
                    'rf': round(float(rf_temp), 1),
                    'lgb': round(float(lgb_temp), 1)
                }
            },
            'rain': {
                'will_rain': bool(rain_proba > 0.5),
                'probability': int(round(float(rain_proba) * 100))
            },
            'confidence': int(confidence),
            'periods': {
                'p1': {'name': 'Matin (04h-12h)', 'temp_estimate': round(float(p1_temp), 1), 'rain_risk': 'high' if rain_proba > 0.6 else 'medium' if rain_proba > 0.3 else 'low'},
                'p2': {'name': 'Après-midi (12h-20h)', 'temp_estimate': round(float(p2_temp), 1), 'rain_risk': 'high' if rain_proba > 0.6 else 'medium' if rain_proba > 0.3 else 'low'},
                'p3': {'name': 'Nuit (20h-04h)', 'temp_estimate': round(float(p3_temp), 1), 'rain_risk': 'high' if rain_proba > 0.6 else 'medium' if rain_proba > 0.3 else 'low'}
            }
        }
        
        forecasts.append(forecast)
    
    return forecasts

def save_predictions(forecasts, metrics):
    output = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics['trained_at'],
        'model_type': 'ensemble',
        'forecasts': forecasts,
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae_ensemble']:.2f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%",
            'ensemble_weights': metrics['weights']
        }
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"✅ Prédictions sauvegardées: {OUTPUT_FILE}")

# ============================================
# MAIN
# ============================================

def main():
    print("=" * 70)
    print("🎯 PRÉDICTIONS MÉTÉO - MODÈLE ENSEMBLISTE")
    print("=" * 70)
    
    data = load_data()
    if not data:
        return
    
    dates = sorted(data.keys())
    
    models = load_models()
    if not models:
        return
    
    print("")
    print("🔮 Génération des prédictions...")
    forecasts = predict_ensemble(data, dates, models)
    
    print("")
    print("=" * 70)
    print("📅 PRÉVISIONS 3 JOURS")
    print("=" * 70)
    
    for f in forecasts:
        print(f"\n{f['day_label']} ({f['date']}):")
        print(f"  🌡️  Température: {f['temperature']['predicted']}°C")
        print(f"      (Ensemble: RF={f['temperature']['ensemble_detail']['rf']}°C, "
              f"LGB={f['temperature']['ensemble_detail']['lgb']}°C)")
        print(f"  🌧️  Pluie: {'OUI' if f['rain']['will_rain'] else 'NON'} ({f['rain']['probability']}%)")
        print(f"  📊 Confiance: {f['confidence']}%")
    
    print("\n" + "=" * 70)
    
    save_predictions(forecasts, models['metrics'])

if __name__ == "__main__":
    main()
