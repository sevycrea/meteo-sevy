#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de prédiction MULTI-HORIZONS avec FEATURES SAISONNIÈRES
Compatible avec les modèles entraînés avec features saisonnières
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

# Paramètres géographiques (Vinelz, Canton de Berne, Suisse)
LATITUDE = 47.09
LONGITUDE = 7.12

# ============================================
# FONCTIONS ASTRONOMIQUES (identiques à train)
# ============================================

def get_day_length(date_obj, latitude):
    """Calcule la durée du jour en heures"""
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
    """Calcule l'élévation solaire maximale en degrés"""
    day_of_year = date_obj.timetuple().tm_yday
    declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
    elevation = 90 - latitude + declination
    return elevation

def get_season(month, day):
    """Retourne la saison météorologique (0-3)"""
    if month in [12, 1, 2]:
        return 0  # Hiver
    elif month in [3, 4, 5]:
        return 1  # Printemps
    elif month in [6, 7, 8]:
        return 2  # Été
    else:
        return 3  # Automne

def get_season_progress(month, day):
    """Retourne la progression dans la saison (0.0 à 1.0)"""
    season_starts = {
        12: 0, 1: 31, 2: 59,
        3: 0, 4: 31, 5: 61,
        6: 0, 7: 30, 8: 61,
        9: 0, 10: 30, 11: 61
    }
    
    if month in [12, 1, 2]:
        days_in_season = 90
        if month == 12:
            day_in_season = day - 1
        elif month == 1:
            day_in_season = 31 + day - 1
        else:
            day_in_season = 62 + day - 1
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
    """Calcule les statistiques glissantes sur les N derniers jours de la même saison"""
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
    """Charger les données enrichies"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        print(f"✅ Données chargées: {len(data)} jours")
        return data
    except Exception as e:
        print(f"❌ Erreur chargement données: {e}")
        return None

def load_models():
    """Charger les modèles et normales saisonnières"""
    try:
        model_temp = joblib.load(f"{MODEL_DIR}/model_temp_seasonal.pkl")
        model_rain = joblib.load(f"{MODEL_DIR}/model_rain_seasonal.pkl")
        seasonal_normals = joblib.load(f"{MODEL_DIR}/seasonal_normals.pkl")
        
        with open(f"{MODEL_DIR}/metrics_seasonal.json", 'r') as f:
            metrics = json.load(f)
        
        print(f"✅ Modèles chargés (entraînés le {metrics['trained_at'][:10]})")
        print(f"   MAE: {metrics['temp_mae']:.2f}°C")
        print(f"   Features saisonnières: {'✅' if metrics.get('seasonal_features') else '❌'}")
        
        return model_temp, model_rain, seasonal_normals, metrics
    except Exception as e:
        print(f"❌ Erreur chargement modèles: {e}")
        return None, None, None, None

def prepare_features_for_prediction(data, dates, today_idx, horizon, seasonal_normals):
    """
    Préparer les features pour une prédiction (AVEC features saisonnières)
    Identique à la fonction d'entraînement
    """
    
    target_idx = today_idx + horizon
    reference_idx = target_idx - horizon
    
    if reference_idx < 7 or target_idx >= len(dates):
        return None
    
    target_date = dates[target_idx]
    
    # Features de base (identique à l'entraînement)
    features = []
    
    # Features des 7 derniers jours
    for j in range(1, 8):
        past_idx = reference_idx - j
        if past_idx < 0:
            return None
            
        past_date = dates[past_idx]
        day_data = data[past_date]
        
        features.append(day_data.get('temp_avg', 15))
        features.append(day_data.get('hum_avg', 70))
        features.append(day_data.get('pressure_avg', 1013))
        features.append(1 if day_data.get('rain', 0) > 0.5 else 0)
        
        for period in ['p1', 'p2', 'p3']:
            features.append(day_data.get(f'{period}_temp_avg', day_data.get('temp_avg', 15)))
            features.append(day_data.get(f'{period}_temp_min', day_data.get('temp_min', 10)))
            features.append(day_data.get(f'{period}_temp_max', day_data.get('temp_max', 20)))
            features.append(day_data.get(f'{period}_temp_range', 5))
            
            features.append(day_data.get(f'{period}_pressure_avg', day_data.get('pressure_avg', 1013)))
            features.append(day_data.get(f'{period}_pressure_range', 5))
            
            features.append(day_data.get(f'{period}_hum_avg', day_data.get('hum_avg', 70)))
            features.append(day_data.get(f'{period}_hum_range', 10))
            
            features.append(day_data.get(f'{period}_wind_max', 10))
            features.append(day_data.get(f'{period}_wind_range', 5))
            
            features.append(1 if day_data.get(f'{period}_has_rain', False) else 0)
    
    # Features du dernier jour connu
    yesterday_idx = reference_idx - 1
    if yesterday_idx < 0:
        return None
        
    yesterday = dates[yesterday_idx]
    yesterday_data = data[yesterday]
    
    features.append(yesterday_data.get('temp_amplitude_day', 10))
    features.append(yesterday_data.get('pressure_drop_max', 5))
    features.append(yesterday_data.get('temp_p1_to_p2', 3))
    features.append(yesterday_data.get('temp_p2_to_p3', -2))
    features.append(yesterday_data.get('gust_max', 0))
    
    features.append(yesterday_data.get('temp_max_day', 20))
    features.append(yesterday_data.get('temp_min_day', 10))
    features.append(yesterday_data.get('temp_total_range', 10))
    features.append(yesterday_data.get('pressure_trend_day', 0))
    features.append(yesterday_data.get('pressure_total_range', 10))
    features.append(yesterday_data.get('hum_range_day', 20))
    
    # Date cible
    target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
    day_of_year = target_datetime.timetuple().tm_yday
    month = target_datetime.month
    
    features.append(day_of_year)
    features.append(month)
    features.append(horizon)
    
    # Tendances
    temps_7d = []
    pressure_7d = []
    for j in range(1, 8):
        idx = reference_idx - j
        if idx >= 0:
            temps_7d.append(data[dates[idx]].get('temp_avg', 15))
            pressure_7d.append(data[dates[idx]].get('pressure_avg', 1013))
    
    if len(temps_7d) >= 7:
        features.append(np.mean(temps_7d[:3]) - np.mean(temps_7d))
        features.append(pressure_7d[0] - pressure_7d[-1])
    else:
        features.append(0)
        features.append(0)
    
    # ============================================
    # FEATURES SAISONNIÈRES
    # ============================================
    
    # 1. Encodage cyclique
    day_of_year_rad = 2 * math.pi * day_of_year / 365.25
    features.append(math.sin(day_of_year_rad))
    features.append(math.cos(day_of_year_rad))
    
    # 2. Saison
    season = get_season(month, target_datetime.day)
    features.append(season)
    season_progress = get_season_progress(month, target_datetime.day)
    features.append(season_progress)
    
    # 3. Paramètres astronomiques
    day_length = get_day_length(target_datetime, LATITUDE)
    solar_elevation = get_solar_elevation(target_datetime, LATITUDE)
    features.append(day_length)
    features.append(solar_elevation)
    
    # Changement de durée du jour
    if target_idx > 0:
        prev_date = datetime.strptime(dates[target_idx - 1], '%Y-%m-%d')
        prev_day_length = get_day_length(prev_date, LATITUDE)
        day_length_change = day_length - prev_day_length
    else:
        day_length_change = 0
    features.append(day_length_change)
    
    # 4. Écart par rapport aux normales
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
        features.append(0)
        features.append(0)
        features.append(0)
    
    # 5. Statistiques saisonnières glissantes
    seasonal_stats = calculate_rolling_seasonal_stats(data, dates, reference_idx, window=30)
    if seasonal_stats:
        features.append(seasonal_stats['temp_mean'])
        features.append(seasonal_stats['temp_std'])
        features.append(seasonal_stats['temp_trend'])
        features.append(seasonal_stats['pressure_mean'])
    else:
        features.append(15.0)
        features.append(5.0)
        features.append(0.0)
        features.append(1013.0)
    
    # 6. Transition saisonnière
    is_season_transition = (season_progress < 0.15 or season_progress > 0.85)
    features.append(1 if is_season_transition else 0)
    
    # 7. Mois cyclique
    month_rad = 2 * math.pi * month / 12
    features.append(math.sin(month_rad))
    features.append(math.cos(month_rad))
    
    return features

def predict_multihorizon(data, dates, model_temp, model_rain, seasonal_normals):
    """Générer les prédictions pour J+0, J+1, J+2"""
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    
    # Trouver l'index du dernier jour avec données
    if today_str in dates:
        today_idx = dates.index(today_str)
    else:
        today_idx = len(dates) - 1
    
    forecasts = []
    
    for horizon in [0, 1, 2]:
        features = prepare_features_for_prediction(data, dates, today_idx, horizon, seasonal_normals)
        
        if features is None:
            continue
        
        # Prédictions
        X = np.array([features])
        temp_pred = model_temp.predict(X)[0]
        rain_proba = model_rain.predict_proba(X)[0][1]
        
        # Date de la prédiction
        pred_date = (datetime.strptime(dates[today_idx], '%Y-%m-%d') + timedelta(days=horizon)).strftime('%Y-%m-%d')
        pred_datetime = datetime.strptime(pred_date, '%Y-%m-%d')
        
        # Confiance (diminue avec l'horizon)
        confidence = max(50, 95 - horizon * 12)
        
        # Estimation min/max
        uncertainty = 0.5 + horizon * 0.3
        
        # Estimations par période (simplifié)
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
                'max_estimate': round(float(temp_pred + uncertainty), 1)
            },
            'rain': {
                'will_rain': bool(rain_proba > 0.5),
                'probability': int(round(float(rain_proba) * 100))
            },
            'confidence': int(confidence),
            'periods': {
                'p1': {
                    'name': 'Matin (04h-12h)',
                    'temp_estimate': round(float(p1_temp), 1),
                    'rain_risk': 'high' if rain_proba > 0.6 else 'medium' if rain_proba > 0.3 else 'low'
                },
                'p2': {
                    'name': 'Après-midi (12h-20h)',
                    'temp_estimate': round(float(p2_temp), 1),
                    'rain_risk': 'high' if rain_proba > 0.6 else 'medium' if rain_proba > 0.3 else 'low'
                },
                'p3': {
                    'name': 'Nuit (20h-04h)',
                    'temp_estimate': round(float(p3_temp), 1),
                    'rain_risk': 'high' if rain_proba > 0.6 else 'medium' if rain_proba > 0.3 else 'low'
                }
            }
        }
        
        forecasts.append(forecast)
    
    return forecasts

def save_predictions(forecasts, metrics):
    """Sauvegarder les prédictions"""
    
    # Convertir les types NumPy en types Python natifs
    def convert_to_python(obj):
        """Convertir récursivement les types NumPy en types Python"""
        if isinstance(obj, dict):
            return {key: convert_to_python(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_python(item) for item in obj]
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.bool_):
            return bool(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj
    
    output = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics['trained_at'],
        'model_type': 'multihorizon_seasonal',
        'forecasts': convert_to_python(forecasts),
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae']:.1f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%"
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
    print("🔮 PRÉDICTIONS MÉTÉO AVEC FEATURES SAISONNIÈRES")
    print("=" * 70)
    
    # 1. Charger données
    data = load_data()
    if not data:
        return
    
    dates = sorted(data.keys())
    
    # 2. Charger modèles
    model_temp, model_rain, seasonal_normals, metrics = load_models()
    if model_temp is None:
        return
    
    # 3. Générer prédictions
    print("")
    print("🔮 Génération des prédictions...")
    forecasts = predict_multihorizon(data, dates, model_temp, model_rain, seasonal_normals)
    
    # 4. Afficher
    print("")
    print("=" * 70)
    print("📅 PRÉVISIONS 3 JOURS")
    print("=" * 70)
    
    for f in forecasts:
        print(f"\n{f['day_label']} ({f['date']}):")
        print(f"  🌡️  Température: {f['temperature']['predicted']}°C")
        print(f"      ({f['temperature']['min_estimate']}°C - {f['temperature']['max_estimate']}°C)")
        print(f"  🌧️  Pluie: {'OUI' if f['rain']['will_rain'] else 'NON'} ({f['rain']['probability']}%)")
        print(f"  📊 Confiance: {f['confidence']}%")
    
    print("\n" + "=" * 70)
    
    # 5. Sauvegarder
    save_predictions(forecasts, metrics)

if __name__ == "__main__":
    main()
