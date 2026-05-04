#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'entraînement MULTI-HORIZONS avec FEATURES SAISONNIÈRES
Ajoute des features astronomiques et saisonnières pour améliorer la précision
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, accuracy_score
import joblib
import math

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
LOG_FILE = f"{BASE_DIR}/logs/training_seasonal.log"

# Paramètres
MIN_TRAIN_DAYS = 100
WALK_FORWARD_START = 100

# Paramètres géographiques (Vinelz, Canton de Berne, Suisse)
LATITUDE = 47.09  # degrés Nord
LONGITUDE = 7.12  # degrés Est

os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ============================================
# FONCTIONS ASTRONOMIQUES
# ============================================

def get_day_length(date_obj, latitude):
    """
    Calcule la durée du jour en heures pour une date et latitude données
    Utilise une approximation simplifiée de l'équation du temps
    """
    day_of_year = date_obj.timetuple().tm_yday
    
    # Déclinaison solaire (approximation)
    declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
    
    # Angle horaire du lever/coucher du soleil
    lat_rad = math.radians(latitude)
    decl_rad = math.radians(declination)
    
    try:
        cos_hour_angle = -math.tan(lat_rad) * math.tan(decl_rad)
        # Limiter entre -1 et 1 pour éviter les erreurs de domaine
        cos_hour_angle = max(-1, min(1, cos_hour_angle))
        hour_angle = math.degrees(math.acos(cos_hour_angle))
        day_length = 2 * hour_angle / 15  # Conversion en heures
    except:
        # Valeur par défaut si calcul impossible
        day_length = 12
    
    return day_length

def get_solar_elevation(date_obj, latitude):
    """
    Calcule l'élévation solaire maximale (à midi) en degrés
    """
    day_of_year = date_obj.timetuple().tm_yday
    
    # Déclinaison solaire
    declination = 23.45 * math.sin(math.radians((360/365) * (day_of_year - 81)))
    
    # Élévation solaire à midi
    elevation = 90 - latitude + declination
    
    return elevation

def get_season(month, day):
    """
    Retourne la saison météorologique (0-3)
    0 = Hiver (Dec-Feb)
    1 = Printemps (Mar-May)
    2 = Été (Jun-Aug)
    3 = Automne (Sep-Nov)
    """
    if month in [12, 1, 2]:
        return 0  # Hiver
    elif month in [3, 4, 5]:
        return 1  # Printemps
    elif month in [6, 7, 8]:
        return 2  # Été
    else:
        return 3  # Automne

def get_season_progress(month, day):
    """
    Retourne la progression dans la saison (0.0 à 1.0)
    """
    # Mapping mois vers jour de début de saison
    season_starts = {
        12: 0, 1: 31, 2: 59,  # Hiver: Dec 1 - Feb 28/29
        3: 0, 4: 31, 5: 61,   # Printemps: Mar 1 - May 31
        6: 0, 7: 30, 8: 61,   # Été: Jun 1 - Aug 31
        9: 0, 10: 30, 11: 61  # Automne: Sep 1 - Nov 30
    }
    
    if month in [12, 1, 2]:
        days_in_season = 90
        if month == 12:
            day_in_season = day - 1
        elif month == 1:
            day_in_season = 31 + day - 1
        else:  # février
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

# ============================================
# FONCTIONS DE CALCUL DES NORMALES
# ============================================

def calculate_seasonal_normals(data, dates):
    """
    Calcule les normales saisonnières (moyennes par saison)
    """
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
    """
    Calcule les statistiques glissantes sur les N derniers jours de la même saison
    """
    if target_idx < window:
        return None
    
    target_date = dates[target_idx]
    target_dt = datetime.strptime(target_date, '%Y-%m-%d')
    target_season = get_season(target_dt.month, target_dt.day)
    
    same_season_temps = []
    same_season_pressures = []
    
    # Regarder les 60 derniers jours pour trouver au moins 'window' jours de la même saison
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
    Préparer les features AVEC features saisonnières avancées
    
    Args:
        target_idx: Index du jour à prédire
        horizon: 0=aujourd'hui, 1=demain, 2=après-demain
        seasonal_normals: Normales saisonnières précalculées
    
    Returns:
        features, temp_target, rain_target
    """
    
    reference_idx = target_idx - horizon
    
    if reference_idx < 7:
        return None, None, None
    
    target_date = dates[target_idx]
    target_data = data[target_date]
    
    # Cibles
    temp_target = target_data.get('temp_avg')
    has_rain = target_data.get('rain', 0) > 0.5
    
    if temp_target is None:
        return None, None, None
    
    # ============================================
    # FEATURES ORIGINALES (comme avant)
    # ============================================
    features = []
    
    # Features des 7 derniers jours
    for j in range(1, 8):
        past_idx = reference_idx - j
        if past_idx < 0:
            return None, None, None
            
        past_date = dates[past_idx]
        day_data = data[past_date]
        
        # Moyennes journalières
        features.append(day_data.get('temp_avg', 15))
        features.append(day_data.get('hum_avg', 70))
        features.append(day_data.get('pressure_avg', 1013))
        features.append(1 if day_data.get('rain', 0) > 0.5 else 0)
        
        # Périodes enrichies
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
    
    # Date cible (features temporelles basiques)
    target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
    day_of_year = target_datetime.timetuple().tm_yday
    month = target_datetime.month
    
    features.append(day_of_year)
    features.append(month)
    features.append(horizon)
    
    # Tendances sur 7 jours
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
    # 🆕 NOUVELLES FEATURES SAISONNIÈRES
    # ============================================
    
    # 1. ENCODAGE CYCLIQUE du jour de l'année (capture la périodicité)
    day_of_year_rad = 2 * math.pi * day_of_year / 365.25
    features.append(math.sin(day_of_year_rad))  # Composante sinusoidale
    features.append(math.cos(day_of_year_rad))  # Composante cosinusoidale
    
    # 2. SAISON MÉTÉOROLOGIQUE
    season = get_season(month, target_datetime.day)
    features.append(season)  # 0=Hiver, 1=Printemps, 2=Été, 3=Automne
    
    # Progression dans la saison (0.0 à 1.0)
    season_progress = get_season_progress(month, target_datetime.day)
    features.append(season_progress)
    
    # 3. PARAMÈTRES ASTRONOMIQUES
    day_length = get_day_length(target_datetime, LATITUDE)
    solar_elevation = get_solar_elevation(target_datetime, LATITUDE)
    
    features.append(day_length)  # Durée du jour en heures (8-16h selon saison)
    features.append(solar_elevation)  # Élévation maximale du soleil en degrés
    
    # Taux de changement de la durée du jour (important au printemps/automne)
    if target_idx > 0:
        prev_date = datetime.strptime(dates[target_idx - 1], '%Y-%m-%d')
        prev_day_length = get_day_length(prev_date, LATITUDE)
        day_length_change = day_length - prev_day_length
    else:
        day_length_change = 0
    features.append(day_length_change)  # minutes/jour
    
    # 4. ÉCART PAR RAPPORT AUX NORMALES SAISONNIÈRES
    if seasonal_normals and season in seasonal_normals:
        normal_temp = seasonal_normals[season]['temp']
        normal_pressure = seasonal_normals[season]['pressure']
        normal_std = seasonal_normals[season]['temp_std']
        
        # Température récente vs normale saisonnière
        recent_temp = yesterday_data.get('temp_avg', 15)
        temp_anomaly = recent_temp - normal_temp
        features.append(temp_anomaly)  # Anomalie de température
        features.append(temp_anomaly / normal_std if normal_std > 0 else 0)  # Anomalie standardisée
        
        # Pression vs normale
        recent_pressure = yesterday_data.get('pressure_avg', 1013)
        pressure_anomaly = recent_pressure - normal_pressure
        features.append(pressure_anomaly)
    else:
        features.append(0)  # temp_anomaly
        features.append(0)  # temp_anomaly_std
        features.append(0)  # pressure_anomaly
    
    # 5. STATISTIQUES SAISONNIÈRES GLISSANTES
    seasonal_stats = calculate_rolling_seasonal_stats(data, dates, reference_idx, window=30)
    if seasonal_stats:
        features.append(seasonal_stats['temp_mean'])
        features.append(seasonal_stats['temp_std'])
        features.append(seasonal_stats['temp_trend'])
        features.append(seasonal_stats['pressure_mean'])
    else:
        features.append(15.0)  # temp_mean par défaut
        features.append(5.0)   # temp_std par défaut
        features.append(0.0)   # temp_trend par défaut
        features.append(1013.0)  # pressure_mean par défaut
    
    # 6. INDICATEURS DE TRANSITION SAISONNIÈRE
    # Détecte les périodes de transition (début/fin de saison) qui sont plus instables
    is_season_transition = (season_progress < 0.15 or season_progress > 0.85)
    features.append(1 if is_season_transition else 0)
    
    # 7. MOIS ENCODÉ EN CYCLIQUE (pour capturer les patterns mensuels)
    month_rad = 2 * math.pi * month / 12
    features.append(math.sin(month_rad))
    features.append(math.cos(month_rad))
    
    return features, temp_target, 1 if has_rain else 0

def train_multihorizon_seasonal(data, dates):
    """
    Entraînement avec features saisonnières
    """
    
    log("=" * 70)
    log("🚀 ENTRAÎNEMENT MULTI-HORIZONS AVEC FEATURES SAISONNIÈRES")
    log("=" * 70)
    
    # Calculer les normales saisonnières
    log("📊 Calcul des normales saisonnières...")
    seasonal_normals = calculate_seasonal_normals(data, dates)
    
    for season, values in seasonal_normals.items():
        season_names = ['Hiver', 'Printemps', 'Été', 'Automne']
        log(f"   {season_names[season]}: {values['temp']:.1f}°C ± {values['temp_std']:.1f}°C, {values['pressure']:.1f} hPa")
    
    X_train = []
    y_temp_train = []
    y_rain_train = []
    
    # Générer des exemples pour les 3 horizons
    log("")
    log("🔨 Génération des features d'entraînement...")
    for i in range(WALK_FORWARD_START, len(dates)):
        target_date = dates[i]
        
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
    
    log(f"📊 Échantillons d'entraînement: {len(X_train)}")
    log(f"📊 Features par échantillon: {X_train.shape[1]} (dont {X_train.shape[1] - 273} saisonnières)")
    log(f"   Répartition par horizon:")
    
    # Compter par horizon
    for h in [0, 1, 2]:
        count = sum(1 for i in range(len(X_train)) if X_train[i][274] == h)  # index ajusté
        log(f"      Horizon {h}: {count} exemples")
    
    # Entraîner les modèles
    log("")
    log("🤖 Entraînement modèle Température...")
    model_temp = RandomForestRegressor(
        n_estimators=200,  # Augmenté pour capturer plus de complexité
        max_depth=15,      # Augmenté pour features saisonnières
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    model_temp.fit(X_train, y_temp_train)
    
    log("🤖 Entraînement modèle Pluie...")
    model_rain = RandomForestClassifier(
        n_estimators=200,
        max_depth=15,
        min_samples_split=5,
        min_samples_leaf=2,
        random_state=42,
        n_jobs=-1
    )
    model_rain.fit(X_train, y_rain_train)
    
    # Évaluation
    temp_pred = model_temp.predict(X_train)
    rain_pred = model_rain.predict(X_train)
    
    mae = mean_absolute_error(y_temp_train, temp_pred)
    acc = accuracy_score(y_rain_train, rain_pred)
    
    log(f"✅ MAE Température: {mae:.2f}°C")
    log(f"✅ Précision Pluie: {acc*100:.1f}%")
    
    # Analyse de l'importance des features
    log("")
    log("🔍 Top 15 features les plus importantes:")
    feature_importance = model_temp.feature_importances_
    top_indices = np.argsort(feature_importance)[-15:][::-1]
    
    feature_names_sample = [
        "temp_J-1", "hum_J-1", "pressure_J-1", "rain_J-1",
        # ... (trop long à lister complètement)
        "day_of_year_sin", "day_of_year_cos", "season", "season_progress",
        "day_length", "solar_elevation", "day_length_change",
        "temp_anomaly", "temp_anomaly_std", "pressure_anomaly"
    ]
    
    for idx in top_indices:
        importance = feature_importance[idx]
        if idx < len(feature_names_sample):
            log(f"   #{idx}: {importance:.4f}")
    
    # Sauvegarder
    joblib.dump(model_temp, f"{MODEL_DIR}/model_temp_seasonal.pkl")
    joblib.dump(model_rain, f"{MODEL_DIR}/model_rain_seasonal.pkl")
    joblib.dump(seasonal_normals, f"{MODEL_DIR}/seasonal_normals.pkl")
    
    metrics = {
        'temp_mae': mae,
        'rain_accuracy': acc,
        'n_samples': len(X_train),
        'n_features': X_train.shape[1],
        'trained_at': datetime.now().isoformat(),
        'horizons': [0, 1, 2],
        'seasonal_features': True,
        'seasonal_normals': {k: {kk: float(vv) for kk, vv in v.items()} for k, v in seasonal_normals.items()}
    }
    
    with open(f"{MODEL_DIR}/metrics_seasonal.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    
    log(f"✅ Modèles sauvegardés dans {MODEL_DIR}")
    
    return model_temp, model_rain, metrics

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🔧 ENTRAÎNEMENT MODÈLE AVEC FEATURES SAISONNIÈRES")
    log("=" * 70)
    
    # 1. Charger données
    data = load_data()
    if not data:
        log("❌ Impossible de charger les données")
        return
    
    dates = sorted(data.keys())
    log(f"📅 Période: {dates[0]} → {dates[-1]}")
    log(f"📅 Total: {len(dates)} jours")
    
    # 2. Entraîner
    model_temp, model_rain, metrics = train_multihorizon_seasonal(data, dates)
    
    # 3. Résumé
    log("")
    log("=" * 70)
    log("✅ ENTRAÎNEMENT TERMINÉ")
    log("=" * 70)
    log(f"📊 Température MAE: ±{metrics['temp_mae']:.2f}°C")
    log(f"🌧️ Pluie Précision: {metrics['rain_accuracy']*100:.1f}%")
    log(f"📈 Échantillons: {metrics['n_samples']}")
    log(f"🔢 Features totales: {metrics['n_features']}")
    log(f"🌍 Features saisonnières: ✅ ACTIVÉES")
    log("=" * 70)

if __name__ == "__main__":
    main()
