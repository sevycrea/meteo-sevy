#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'entraînement du modèle de prévision météo
Entraîne un modèle RandomForest sur les données historiques
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_absolute_error, accuracy_score
import joblib

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Documents/Météo"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
LOG_FILE = f"{BASE_DIR}/logs/training.log"

# Créer les dossiers si nécessaire
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
    """Charger les données historiques"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"✅ Données chargées: {len(data)} jours")
        return data
    except Exception as e:
        log(f"❌ Erreur chargement données: {e}")
        return None

def prepare_features(data):
    """
    Préparer les features pour le modèle
    
    Features utilisées:
    - Température des 7 derniers jours
    - Humidité des 7 derniers jours
    - Pression des 7 derniers jours
    - Pluie des 7 derniers jours
    - Jour de l'année
    - Mois
    """
    
    dates = sorted(data.keys())
    
    X_temp = []  # Features pour prédiction température
    y_temp = []  # Target température
    
    X_rain = []  # Features pour prédiction pluie
    y_rain = []  # Target pluie (0/1)
    
    # On a besoin de 7 jours d'historique pour prédire J+1
    for i in range(7, len(dates)):
        current_date = dates[i]
        
        # Features des 7 derniers jours
        temps_7d = [data[dates[i-j]]['temp_avg'] for j in range(1, 8)]
        hum_7d = [data[dates[i-j]].get('hum_avg', 70) for j in range(1, 8)]
        pressure_7d = [data[dates[i-j]].get('pressure_avg', 1013) for j in range(1, 8)]
        rain_7d = [1 if data[dates[i-j]].get('rain', 0) > 0 else 0 for j in range(1, 8)]
        
        # Ajouter les variations (amplitude) pour améliorer le modèle
        temp_range = data[dates[i-1]]['temp_max'] - data[dates[i-1]]['temp_min']  # Amplitude hier
        hum_range = data[dates[i-1]].get('hum_max', 100) - data[dates[i-1]].get('hum_min', 0)
        pressure_range = data[dates[i-1]].get('pressure_max', 1030) - data[dates[i-1]].get('pressure_min', 990)
        gust_max_yesterday = data[dates[i-1]].get('gust_max', 0)
        
        # Date features
        dt = datetime.strptime(current_date, '%Y-%m-%d')
        day_of_year = dt.timetuple().tm_yday
        month = dt.month
        
        # Tendance température (moyenne 3 derniers jours vs 7 derniers jours)
        temp_trend = np.mean(temps_7d[:3]) - np.mean(temps_7d)
        
        # Tendance pression (indicateur météo important)
        pressure_trend = pressure_7d[0] - pressure_7d[-1]
        
        # Features combinées (plus de données = meilleure prédiction)
        features = (temps_7d + hum_7d + pressure_7d + rain_7d + 
                   [day_of_year, month, temp_trend, temp_range, hum_range, 
                    pressure_range, gust_max_yesterday, pressure_trend])
        
        # Targets (ce qu'on veut prédire)
        target_temp = data[current_date]['temp_avg']
        target_rain = 1 if data[current_date].get('rain', 0) > 0.5 else 0
        
        X_temp.append(features)
        y_temp.append(target_temp)
        
        X_rain.append(features)
        y_rain.append(target_rain)
    
    return np.array(X_temp), np.array(y_temp), np.array(X_rain), np.array(y_rain)

def train_models(X_temp, y_temp, X_rain, y_rain):
    """Entraîner les modèles de prédiction"""
    
    log("📊 Entraînement des modèles...")
    
    # Split train/test
    X_temp_train, X_temp_test, y_temp_train, y_temp_test = train_test_split(
        X_temp, y_temp, test_size=0.2, random_state=42
    )
    
    X_rain_train, X_rain_test, y_rain_train, y_rain_test = train_test_split(
        X_rain, y_rain, test_size=0.2, random_state=42
    )
    
    # Modèle pour la température
    log("  🌡️ Entraînement modèle température...")
    model_temp = RandomForestRegressor(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        n_jobs=-1
    )
    model_temp.fit(X_temp_train, y_temp_train)
    
    # Modèle pour la pluie
    log("  🌧️ Entraînement modèle pluie...")
    model_rain = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
        n_jobs=-1
    )
    model_rain.fit(X_rain_train, y_rain_train)
    
    # Évaluation
    temp_pred = model_temp.predict(X_temp_test)
    temp_mae = mean_absolute_error(y_temp_test, temp_pred)
    
    rain_pred = model_rain.predict(X_rain_test)
    rain_acc = accuracy_score(y_rain_test, rain_pred)
    
    log(f"  ✅ Température MAE: {temp_mae:.2f}°C")
    log(f"  ✅ Pluie Précision: {rain_acc*100:.1f}%")
    
    return model_temp, model_rain, temp_mae, rain_acc

def save_models(model_temp, model_rain, temp_mae, rain_acc):
    """Sauvegarder les modèles"""
    
    log("💾 Sauvegarde des modèles...")
    
    # Sauvegarder les modèles
    joblib.dump(model_temp, f"{MODEL_DIR}/model_temp.pkl")
    joblib.dump(model_rain, f"{MODEL_DIR}/model_rain.pkl")
    
    # Sauvegarder les métriques
    metrics = {
        'trained_at': datetime.now().isoformat(),
        'temp_mae': float(temp_mae),
        'rain_accuracy': float(rain_acc)
    }
    
    with open(f"{MODEL_DIR}/metrics.json", 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    
    log("✅ Modèles sauvegardés")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 60)
    log("🤖 ENTRAÎNEMENT MODÈLE PRÉVISION MÉTÉO")
    log("=" * 60)
    
    # 1. Charger les données
    data = load_data()
    if not data or len(data) < 30:
        log("❌ Pas assez de données (minimum 30 jours requis)")
        return
    
    # 2. Préparer les features
    log("🔧 Préparation des features...")
    X_temp, y_temp, X_rain, y_rain = prepare_features(data)
    log(f"  ✅ {len(X_temp)} échantillons créés")
    
    # 3. Entraîner les modèles
    model_temp, model_rain, temp_mae, rain_acc = train_models(X_temp, y_temp, X_rain, y_rain)
    
    # 4. Sauvegarder
    save_models(model_temp, model_rain, temp_mae, rain_acc)
    
    log("=" * 60)
    log("✅ ENTRAÎNEMENT TERMINÉ AVEC SUCCÈS")
    log(f"📊 Précision température: ±{temp_mae:.2f}°C")
    log(f"📊 Précision pluie: {rain_acc*100:.1f}%")
    log("=" * 60)

if __name__ == "__main__":
    main()
