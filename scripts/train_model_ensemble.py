#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'entraînement MODÈLE ENSEMBLISTE
Combine Random Forest + XGBoost + LightGBM pour précision maximale
"""

import json
import os
from datetime import datetime
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, accuracy_score
import lightgbm as lgb
import joblib
import math

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
LOG_FILE = f"{BASE_DIR}/logs/training_ensemble.log"

MIN_TRAIN_DAYS = 100
WALK_FORWARD_START = 100

# Paramètres géographiques (Vinelz, Canton de Berne, Suisse)
LATITUDE = 47.09
LONGITUDE = 7.12

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ============================================
# FONCTIONS ASTRONOMIQUES (identiques)
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
        return 0
    elif month in [3, 4, 5]:
        return 1
    elif month in [6, 7, 8]:
        return 2
    else:
        return 3

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

def calculate_seasonal_normals(data, dates):
    """Calcule les normales saisonnières"""
    seasonal_temps = {0: [], 1: [], 2: [], 3: []}
    seasonal_pressures = {0: [], 1: [], 2: [], 3: []}
    
    for date_str in dates:
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        season = get_season(date_obj.month, date_obj.day)
        
        day_data = data[date_str]
        if 'temp_avg' in day_data:
            seasonal_temps[season].append(day_data['temp_avg'])
        if 'pressure_avg' in day_data:
            seasonal_pressures[season].append(day_data['pressure_avg'])
    
    normals = {}
    for season in range(4):
        normals[season] = {
            'temp': np.mean(seasonal_temps[season]) if seasonal_temps[season] else 15.0,
            'pressure': np.mean(seasonal_pressures[season]) if seasonal_pressures[season] else 1013.0,
            'temp_std': np.std(seasonal_temps[season]) if len(seasonal_temps[season]) > 1 else 5.0
        }
    
    return normals

def calculate_rolling_seasonal_stats(data, dates, target_idx, window=30):
    """Calcule les statistiques glissantes"""
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

def log(message):
    """Écrire dans le fichier log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message)

def load_data():
    """Charger les données enrichies"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"✅ Données enrichies chargées: {len(data)} jours")
        return data
    except Exception as e:
        log(f"❌ Erreur chargement données: {e}")
        return None

def prepare_features_with_seasonal(data, dates, target_idx, horizon=1, seasonal_normals=None):
    """
    Préparer les features avec saisonnalité (fonction identique au script saisonnier)
    """
    reference_idx = target_idx - horizon
    
    if reference_idx < 7:
        return None, None, None
    
    target_date = dates[target_idx]
    target_data = data[target_date]
    
    temp_target = target_data.get('temp_avg')
    has_rain = target_data.get('rain', 0) > 0.5
    
    if temp_target is None:
        return None, None, None
    
    features = []
    
    # Features des 7 derniers jours (code identique au script saisonnier)
    for j in range(1, 8):
        past_idx = reference_idx - j
        if past_idx < 0:
            return None, None, None
            
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
    
    yesterday_idx = reference_idx - 1
    if yesterday_idx < 0:
        return None, None, None
        
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
    
    target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
    day_of_year = target_datetime.timetuple().tm_yday
    month = target_datetime.month
    
    features.append(day_of_year)
    features.append(month)
    features.append(horizon)
    
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
    
    # Features saisonnières
    day_of_year_rad = 2 * math.pi * day_of_year / 365.25
    features.append(math.sin(day_of_year_rad))
    features.append(math.cos(day_of_year_rad))
    
    season = get_season(month, target_datetime.day)
    features.append(season)
    season_progress = get_season_progress(month, target_datetime.day)
    features.append(season_progress)
    
    day_length = get_day_length(target_datetime, LATITUDE)
    solar_elevation = get_solar_elevation(target_datetime, LATITUDE)
    features.append(day_length)
    features.append(solar_elevation)
    
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
        features.append(0)
        features.append(0)
        features.append(0)
    
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
    
    is_season_transition = (season_progress < 0.15 or season_progress > 0.85)
    features.append(1 if is_season_transition else 0)
    
    month_rad = 2 * math.pi * month / 12
    features.append(math.sin(month_rad))
    features.append(math.cos(month_rad))
    
    return features, temp_target, 1 if has_rain else 0

def train_ensemble(data, dates):
    """
    Entraînement du modèle ENSEMBLISTE
    """
    
    log("=" * 70)
    log("🎯 ENTRAÎNEMENT MODÈLE ENSEMBLISTE (RF + LightGBM)")
    log("=" * 70)
    
    # Calculer normales
    log("📊 Calcul des normales saisonnières...")
    seasonal_normals = calculate_seasonal_normals(data, dates)
    
    X_train = []
    y_temp_train = []
    y_rain_train = []
    
    log("")
    log("🔨 Génération des features...")
    for i in range(WALK_FORWARD_START, len(dates)):
        for horizon in [0, 1, 2]:
            features, temp_target, rain_target = prepare_features_with_seasonal(
                data, dates, i, horizon, seasonal_normals
            )
            
            if features is not None:
                X_train.append(features)
                y_temp_train.append(temp_target)
                y_rain_train.append(rain_target)
    
    X_train = np.array(X_train)
    y_temp_train = np.array(y_temp_train)
    y_rain_train = np.array(y_rain_train)
    
    log(f"📊 Échantillons: {len(X_train)}")
    log(f"📊 Features: {X_train.shape[1]}")
    log("")
    
    # ============================================
    # MODÈLE 1 : RANDOM FOREST
    # ============================================
    
    log("🌲 Entraînement Random Forest...")
    rf_temp = RandomForestRegressor(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    rf_temp.fit(X_train, y_temp_train)
    
    rf_rain = RandomForestClassifier(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    rf_rain.fit(X_train, y_rain_train)
    
    rf_temp_pred = rf_temp.predict(X_train)
    rf_mae = mean_absolute_error(y_temp_train, rf_temp_pred)
    log(f"   MAE: {rf_mae:.3f}°C")
    
    # ============================================
    # MODÈLE 2 : LIGHTGBM
    # ============================================
    
    log("💡 Entraînement LightGBM...")
    lgb_temp = lgb.LGBMRegressor(
        n_estimators=200,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbose=-1
    )
    lgb_temp.fit(X_train, y_temp_train)
    
    lgb_rain = lgb.LGBMClassifier(
        n_estimators=200,
        max_depth=8,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        n_jobs=-1,
        verbose=-1
    )
    lgb_rain.fit(X_train, y_rain_train)
    
    lgb_temp_pred = lgb_temp.predict(X_train)
    lgb_mae = mean_absolute_error(y_temp_train, lgb_temp_pred)
    log(f"   MAE: {lgb_mae:.3f}°C")
    
    # ============================================
    # ENSEMBLE : MOYENNE PONDÉRÉE (RF + LightGBM)
    # ============================================
    
    log("")
    log("🎯 Calcul de l'ensemble (moyenne pondérée)...")
    
    # Poids basés sur les MAE inverses (2 modèles)
    total_inverse = (1/rf_mae + 1/lgb_mae)
    weight_rf = (1/rf_mae) / total_inverse
    weight_lgb = (1/lgb_mae) / total_inverse
    
    log(f"   Poids RF:      {weight_rf:.3f}")
    log(f"   Poids LightGBM:{weight_lgb:.3f}")
    
    # Prédiction ensembliste
    ensemble_temp_pred = (
        weight_rf * rf_temp_pred +
        weight_lgb * lgb_temp_pred
    )
    
    # Pour la pluie, on fait un vote majoritaire pondéré
    rf_rain_prob = rf_rain.predict_proba(X_train)[:, 1]
    lgb_rain_prob = lgb_rain.predict_proba(X_train)[:, 1]
    
    ensemble_rain_prob = (
        weight_rf * rf_rain_prob +
        weight_lgb * lgb_rain_prob
    )
    ensemble_rain_pred = (ensemble_rain_prob > 0.5).astype(int)
    
    # Métriques ensemble
    ensemble_mae = mean_absolute_error(y_temp_train, ensemble_temp_pred)
    ensemble_acc = accuracy_score(y_rain_train, ensemble_rain_pred)
    
    log("")
    log("=" * 70)
    log("📊 RÉSULTATS")
    log("=" * 70)
    log(f"   Random Forest:  MAE {rf_mae:.3f}°C")
    log(f"   LightGBM:       MAE {lgb_mae:.3f}°C")
    log(f"   ENSEMBLE:       MAE {ensemble_mae:.3f}°C ⭐")
    log("")
    log(f"   Précision pluie: {ensemble_acc*100:.1f}%")
    
    # Amélioration vs meilleur modèle individuel
    best_individual = min(rf_mae, lgb_mae)
    improvement = ((best_individual - ensemble_mae) / best_individual) * 100
    log(f"   Amélioration vs meilleur: {improvement:+.1f}%")
    
    # Sauvegarder
    log("")
    log("💾 Sauvegarde des modèles...")
    joblib.dump(rf_temp, f"{MODEL_DIR}/ensemble_rf_temp.pkl")
    joblib.dump(rf_rain, f"{MODEL_DIR}/ensemble_rf_rain.pkl")
    joblib.dump(lgb_temp, f"{MODEL_DIR}/ensemble_lgb_temp.pkl")
    joblib.dump(lgb_rain, f"{MODEL_DIR}/ensemble_lgb_rain.pkl")
    joblib.dump(seasonal_normals, f"{MODEL_DIR}/ensemble_seasonal_normals.pkl")
    
    # Sauvegarder les poids
    weights = {
        'rf': float(weight_rf),
        'lgb': float(weight_lgb)
    }
    joblib.dump(weights, f"{MODEL_DIR}/ensemble_weights.pkl")
    
    metrics = {
        'temp_mae_rf': float(rf_mae),
        'temp_mae_lgb': float(lgb_mae),
        'temp_mae_ensemble': float(ensemble_mae),
        'rain_accuracy': float(ensemble_acc),
        'weights': weights,
        'improvement_percent': float(improvement),
        'n_samples': int(len(X_train)),
        'n_features': int(X_train.shape[1]),
        'trained_at': datetime.now().isoformat(),
        'model_type': 'ensemble_rf_lgb'
    }
    
    with open(f"{MODEL_DIR}/metrics_ensemble.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    
    log("✅ Modèles sauvegardés")
    log("")
    log("=" * 70)
    log("✅ ENTRAÎNEMENT TERMINÉ")
    log("=" * 70)
    
    return metrics

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🔧 ENTRAÎNEMENT MODÈLE ENSEMBLISTE")
    log("=" * 70)
    
    data = load_data()
    if not data:
        return
    
    dates = sorted(data.keys())
    log(f"📅 Période: {dates[0]} → {dates[-1]}")
    log(f"📅 Total: {len(dates)} jours")
    log("")
    
    metrics = train_ensemble(data, dates)
    
    log("")
    log(f"🎯 MAE Final: {metrics['temp_mae_ensemble']:.3f}°C")
    log(f"🎯 Amélioration: {metrics['improvement_percent']:+.1f}%")
    log("=" * 70)

if __name__ == "__main__":
    main()
