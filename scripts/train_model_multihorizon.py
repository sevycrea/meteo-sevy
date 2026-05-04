#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'entraînement MULTI-HORIZONS avec données 3x8h
Entraîne le modèle pour prédire J+0, J+1 ET J+2
"""

import json
import os
from datetime import datetime
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, accuracy_score
import joblib

# ============================================
# CONFIGURATION
# ============================================

# Chemins — relatifs à la racine du repo
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "data", "meteo_data_enriched.json")
MODEL_DIR = os.path.join(BASE_DIR, "data", "models")
LOG_FILE  = os.path.join(BASE_DIR, "logs", "training_multihorizon.log")

# Paramètres
MIN_TRAIN_DAYS = 100
WALK_FORWARD_START = 100

os.makedirs(MODEL_DIR, exist_ok=True)
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

def prepare_features(data, dates, target_idx, horizon=1):
    """
    Préparer les features pour prédire un jour avec un horizon donné
    
    Args:
        target_idx: Index du jour à prédire
        horizon: 0=aujourd'hui, 1=demain, 2=après-demain
    
    Returns:
        features, temp_target, rain_target
    """
    
    # Pour horizon=1 (demain), on utilise les données jusqu'à aujourd'hui (target_idx-1)
    # Pour horizon=2 (après-demain), on utilise les données jusqu'à aujourd'hui (target_idx-2)
    reference_idx = target_idx - horizon
    
    # Vérifier qu'on a assez d'historique
    if reference_idx < 7:
        return None, None, None
    
    target_date = dates[target_idx]
    target_data = data[target_date]
    
    # Cibles
    temp_target = target_data.get('temp_avg')
    has_rain = target_data.get('rain', 0) > 0.5
    
    if temp_target is None:
        return None, None, None
    
    # Features des 7 derniers jours (depuis reference_idx)
    features = []
    
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
        
        # Périodes - ENRICHIES
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
    
    # Features du dernier jour connu (reference_idx - 1)
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
    
    # Date cible
    target_datetime = datetime.strptime(target_date, '%Y-%m-%d')
    features.append(target_datetime.timetuple().tm_yday)
    features.append(target_datetime.month)
    
    # FEATURE CRITIQUE : Horizon
    features.append(horizon)  # 0, 1, ou 2
    
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
    
    return features, temp_target, 1 if has_rain else 0

def train_multihorizon(data, dates):
    """
    Entraînement avec PLUSIEURS horizons (J+0, J+1, J+2)
    """
    
    log("=" * 70)
    log("🚀 ENTRAÎNEMENT MULTI-HORIZONS (J+0, J+1, J+2)")
    log("=" * 70)
    
    X_train = []
    y_temp_train = []
    y_rain_train = []
    
    # Générer des exemples pour les 3 horizons
    for i in range(WALK_FORWARD_START, len(dates)):
        target_date = dates[i]
        
        # Entraîner sur les 3 horizons
        for horizon in [0, 1, 2]:
            features, temp_target, rain_target = prepare_features(data, dates, i, horizon)
            
            if features is not None:
                X_train.append(features)
                y_temp_train.append(temp_target)
                y_rain_train.append(rain_target)
    
    X_train = np.array(X_train)
    y_temp_train = np.array(y_temp_train)
    y_rain_train = np.array(y_rain_train)
    
    log(f"📊 Échantillons d'entraînement: {len(X_train)}")
    log(f"📊 Features par échantillon: {X_train.shape[1]}")
    log(f"   Répartition par horizon:")
    
    # Compter par horizon
    for h in [0, 1, 2]:
        count = sum(1 for i in range(len(X_train)) if X_train[i][-3] == h)
        log(f"      Horizon {h}: {count} exemples")
    
    # Entraîner les modèles
    log("")
    log("🤖 Entraînement modèle Température...")
    model_temp = RandomForestRegressor(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
    model_temp.fit(X_train, y_temp_train)
    
    log("🤖 Entraînement modèle Pluie...")
    model_rain = RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
    model_rain.fit(X_train, y_rain_train)
    
    # Évaluation
    temp_pred = model_temp.predict(X_train)
    rain_pred = model_rain.predict(X_train)
    
    mae = mean_absolute_error(y_temp_train, temp_pred)
    acc = accuracy_score(y_rain_train, rain_pred)
    
    log(f"✅ MAE Température: {mae:.2f}°C")
    log(f"✅ Précision Pluie: {acc*100:.1f}%")
    
    # Sauvegarder
    joblib.dump(model_temp, f"{MODEL_DIR}/model_temp_multihorizon.pkl")
    joblib.dump(model_rain, f"{MODEL_DIR}/model_rain_multihorizon.pkl")
    
    metrics = {
        'temp_mae': mae,
        'rain_accuracy': acc,
        'n_samples': len(X_train),
        'n_features': X_train.shape[1],
        'trained_at': datetime.now().isoformat(),
        'horizons': [0, 1, 2]
    }
    
    with open(f"{MODEL_DIR}/metrics_multihorizon.json", 'w') as f:
        json.dump(metrics, f, indent=2)
    
    log(f"✅ Modèles sauvegardés dans {MODEL_DIR}")
    
    return model_temp, model_rain, metrics

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🔧 ENTRAÎNEMENT MODÈLE MULTI-HORIZONS")
    log("=" * 70)
    
    # 1. Charger données
    data = load_data()
    if not data:
        log("❌ Impossible de charger les données")
        return
    
    dates = sorted(data.keys())
    log(f"📅 Période: {dates[0]} → {dates[-1]}")
    
    # 2. Entraîner
    model_temp, model_rain, metrics = train_multihorizon(data, dates)
    
    # 3. Résumé
    log("")
    log("=" * 70)
    log("✅ ENTRAÎNEMENT TERMINÉ")
    log("=" * 70)
    log(f"📊 Température MAE: ±{metrics['temp_mae']:.1f}°C")
    log(f"🌧️ Pluie Précision: {metrics['rain_accuracy']*100:.0f}%")
    log(f"📈 Échantillons: {metrics['n_samples']}")
    log(f"🔢 Features: {metrics['n_features']}")
    log("=" * 70)

if __name__ == "__main__":
    main()
