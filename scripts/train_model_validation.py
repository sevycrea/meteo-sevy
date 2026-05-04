#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'entraînement avec Walk-Forward Validation
Entraîne progressivement sur les 270 jours pour auto-apprentissage
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
from sklearn.ensemble import RandomForestRegressor, RandomForestClassifier
from sklearn.metrics import mean_absolute_error, accuracy_score
import joblib

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
LOG_FILE = f"{BASE_DIR}/logs/training_validation.log"

# Paramètres de validation
MIN_TRAIN_DAYS = 100  # Minimum de jours pour commencer l'entraînement
WALK_FORWARD_START = 100  # Commencer la validation au jour 100

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

def prepare_features_single(data, dates, target_idx):
    """
    Préparer les features pour prédire UN jour spécifique
    
    Args:
        data: Dictionnaire complet des données
        dates: Liste triée des dates disponibles
        target_idx: Index du jour à prédire
    
    Returns:
        features, target_temp, target_rain
    """
    
    if target_idx < 7:
        return None, None, None  # Pas assez d'historique
    
    target_date = dates[target_idx]
    
    # Features des 7 derniers jours AVANT le jour cible
    temps_7d = [data[dates[target_idx-j]]['temp_avg'] for j in range(1, 8)]
    hum_7d = [data[dates[target_idx-j]].get('hum_avg', 70) for j in range(1, 8)]
    pressure_7d = [data[dates[target_idx-j]].get('pressure_avg', 1013) for j in range(1, 8)]
    rain_7d = [1 if data[dates[target_idx-j]].get('rain', 0) > 0 else 0 for j in range(1, 8)]
    
    # Variations d'hier
    yesterday = dates[target_idx-1]
    temp_range = data[yesterday]['temp_max'] - data[yesterday]['temp_min']
    hum_range = data[yesterday].get('hum_max', 100) - data[yesterday].get('hum_min', 0)
    pressure_range = data[yesterday].get('pressure_max', 1030) - data[yesterday].get('pressure_min', 990)
    wind_max_yesterday = data[yesterday].get('wind_max', 0)
    
    # Date features
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    day_of_year = dt.timetuple().tm_yday
    month = dt.month
    
    # Tendances
    temp_trend = np.mean(temps_7d[:3]) - np.mean(temps_7d)
    pressure_trend = pressure_7d[0] - pressure_7d[-1]
    
    # Features combinées
    features = (temps_7d + hum_7d + pressure_7d + rain_7d + 
               [day_of_year, month, temp_trend, temp_range, hum_range, 
                pressure_range, wind_max_yesterday, pressure_trend])
    
    # Targets (ce qu'on veut prédire)
    target_temp = data[target_date]['temp_avg']
    target_rain = 1 if data[target_date].get('rain', 0) > 0.5 else 0
    
    return np.array(features), target_temp, target_rain

def walk_forward_validation(data, dates):
    """
    Validation temporelle : entraîner progressivement et tester sur chaque jour
    """
    
    log("=" * 70)
    log("🔄 WALK-FORWARD VALIDATION")
    log("=" * 70)
    
    results = {
        'predictions': [],
        'errors_temp': [],
        'errors_rain': []
    }
    
    total_days = len(dates)
    
    for day_idx in range(WALK_FORWARD_START, total_days):
        current_date = dates[day_idx]
        
        # 1. Préparer les données d'entraînement (tout ce qui précède)
        X_temp_train = []
        y_temp_train = []
        X_rain_train = []
        y_rain_train = []
        
        for train_idx in range(7, day_idx):  # De 7 à day_idx exclu
            feat, temp_target, rain_target = prepare_features_single(data, dates, train_idx)
            if feat is not None:
                X_temp_train.append(feat)
                y_temp_train.append(temp_target)
                X_rain_train.append(feat)
                y_rain_train.append(rain_target)
        
        X_temp_train = np.array(X_temp_train)
        y_temp_train = np.array(y_temp_train)
        X_rain_train = np.array(X_rain_train)
        y_rain_train = np.array(y_rain_train)
        
        # 2. Entraîner les modèles sur les données disponibles
        model_temp = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        model_temp.fit(X_temp_train, y_temp_train)
        
        model_rain = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )
        model_rain.fit(X_rain_train, y_rain_train)
        
        # 3. Préparer les features pour prédire le jour actuel
        feat_test, temp_actual, rain_actual = prepare_features_single(data, dates, day_idx)
        
        if feat_test is None:
            continue
        
        # 4. Faire la prédiction
        temp_pred = model_temp.predict([feat_test])[0]
        rain_pred = model_rain.predict([feat_test])[0]
        
        # 5. Comparer avec la réalité
        temp_error = abs(temp_pred - temp_actual)
        rain_correct = 1 if rain_pred == rain_actual else 0
        
        # 6. Stocker les résultats
        results['predictions'].append({
            'date': current_date,
            'train_days': day_idx - 7,
            'temp_pred': round(temp_pred, 1),
            'temp_actual': round(temp_actual, 1),
            'temp_error': round(temp_error, 2),
            'rain_pred': bool(rain_pred),
            'rain_actual': bool(rain_actual),
            'rain_correct': bool(rain_correct)
        })
        
        results['errors_temp'].append(temp_error)
        results['errors_rain'].append(rain_correct)
        
        # Log tous les 10 jours
        if (day_idx - WALK_FORWARD_START) % 10 == 0:
            progress = ((day_idx - WALK_FORWARD_START) / (total_days - WALK_FORWARD_START)) * 100
            log(f"📊 Jour {day_idx}/{total_days} ({progress:.1f}%) - "
                f"MAE temp: {np.mean(results['errors_temp']):.2f}°C - "
                f"Acc pluie: {np.mean(results['errors_rain'])*100:.1f}%")
    
    return results

def analyze_results(results):
    """Analyser les résultats de la validation"""
    
    log("\n" + "=" * 70)
    log("📈 ANALYSE DES RÉSULTATS")
    log("=" * 70)
    
    # Métriques globales
    mae_temp = np.mean(results['errors_temp'])
    acc_rain = np.mean(results['errors_rain']) * 100
    
    log(f"\n📊 Performance Globale:")
    log(f"   Température MAE: {mae_temp:.2f}°C")
    log(f"   Pluie Précision: {acc_rain:.1f}%")
    log(f"   Nombre de prédictions: {len(results['predictions'])}")
    
    # Évolution dans le temps (premiers 50 jours vs derniers 50 jours)
    mid_point = len(results['errors_temp']) // 2
    
    mae_first_half = np.mean(results['errors_temp'][:mid_point])
    mae_second_half = np.mean(results['errors_temp'][mid_point:])
    
    acc_first_half = np.mean(results['errors_rain'][:mid_point]) * 100
    acc_second_half = np.mean(results['errors_rain'][mid_point:]) * 100
    
    log(f"\n📈 Évolution:")
    log(f"   Température MAE - Début: {mae_first_half:.2f}°C, Fin: {mae_second_half:.2f}°C")
    log(f"   Pluie Précision - Début: {acc_first_half:.1f}%, Fin: {acc_second_half:.1f}%")
    
    improvement_temp = ((mae_first_half - mae_second_half) / mae_first_half) * 100
    improvement_rain = acc_second_half - acc_first_half
    
    if improvement_temp > 0:
        log(f"   ✅ Amélioration température: {improvement_temp:.1f}%")
    else:
        log(f"   ⚠️ Dégradation température: {abs(improvement_temp):.1f}%")
    
    if improvement_rain > 0:
        log(f"   ✅ Amélioration pluie: +{improvement_rain:.1f}%")
    else:
        log(f"   ⚠️ Dégradation pluie: {improvement_rain:.1f}%")
    
    # Pires prédictions
    log(f"\n❌ 5 Pires Prédictions (Température):")
    sorted_preds = sorted(results['predictions'], key=lambda x: x['temp_error'], reverse=True)
    for pred in sorted_preds[:5]:
        log(f"   {pred['date']}: Prédit {pred['temp_pred']}°C, Réel {pred['temp_actual']}°C, "
            f"Erreur {pred['temp_error']}°C")
    
    return mae_temp, acc_rain

def train_final_model(data, dates):
    """Entraîner le modèle final sur TOUTES les données"""
    
    log("\n" + "=" * 70)
    log("🎓 ENTRAÎNEMENT DU MODÈLE FINAL")
    log("=" * 70)
    
    X_temp = []
    y_temp = []
    X_rain = []
    y_rain = []
    
    for idx in range(7, len(dates)):
        feat, temp_target, rain_target = prepare_features_single(data, dates, idx)
        if feat is not None:
            X_temp.append(feat)
            y_temp.append(temp_target)
            X_rain.append(feat)
            y_rain.append(rain_target)
    
    X_temp = np.array(X_temp)
    y_temp = np.array(y_temp)
    X_rain = np.array(X_rain)
    y_rain = np.array(y_rain)
    
    log(f"   {len(X_temp)} échantillons pour l'entraînement final")
    
    # Entraîner
    model_temp = RandomForestRegressor(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    model_temp.fit(X_temp, y_temp)
    
    model_rain = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42, n_jobs=-1)
    model_rain.fit(X_rain, y_rain)
    
    # Sauvegarder
    joblib.dump(model_temp, f"{MODEL_DIR}/model_temp.pkl")
    joblib.dump(model_rain, f"{MODEL_DIR}/model_rain.pkl")
    
    log("   ✅ Modèles finaux sauvegardés")
    
    return model_temp, model_rain

def save_results(results, mae_temp, acc_rain):
    """Sauvegarder les résultats de validation"""
    
    output = {
        'validation_date': datetime.now().isoformat(),
        'metrics': {
            'temperature_mae': float(mae_temp),
            'rain_accuracy': float(acc_rain / 100),
            'predictions_count': len(results['predictions'])
        },
        'all_predictions': results['predictions']
    }
    
    with open(f"{MODEL_DIR}/validation_results.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    # Aussi mettre à jour metrics.json
    metrics = {
        'trained_at': datetime.now().isoformat(),
        'temp_mae': float(mae_temp),
        'rain_accuracy': float(acc_rain / 100)
    }
    
    with open(f"{MODEL_DIR}/metrics.json", 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    
    log(f"\n💾 Résultats sauvegardés dans {MODEL_DIR}/")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🤖 ENTRAÎNEMENT AVEC WALK-FORWARD VALIDATION")
    log("=" * 70)
    
    # 1. Charger les données
    data = load_data()
    if not data or len(data) < MIN_TRAIN_DAYS:
        log(f"❌ Pas assez de données (minimum {MIN_TRAIN_DAYS} jours requis)")
        return
    
    dates = sorted(data.keys())
    log(f"📅 Période: {dates[0]} → {dates[-1]}")
    log(f"📊 {len(dates)} jours de données disponibles")
    
    # 2. Walk-Forward Validation
    results = walk_forward_validation(data, dates)
    
    # 3. Analyser les résultats
    mae_temp, acc_rain = analyze_results(results)
    
    # 4. Entraîner le modèle final
    model_temp, model_rain = train_final_model(data, dates)
    
    # 5. Sauvegarder
    save_results(results, mae_temp, acc_rain)
    
    log("\n" + "=" * 70)
    log("✅ ENTRAÎNEMENT TERMINÉ AVEC SUCCÈS")
    log("=" * 70)
    log(f"📊 Température MAE: ±{mae_temp:.2f}°C")
    log(f"📊 Pluie Précision: {acc_rain:.1f}%")
    log("=" * 70)

if __name__ == "__main__":
    main()
