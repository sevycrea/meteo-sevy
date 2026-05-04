#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script d'entraînement avec données 3x8h et Walk-Forward Validation
Utilise les périodes p1/p2/p3 pour améliorer la précision
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
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
LOG_FILE = f"{BASE_DIR}/logs/training_3x8h.log"

# Paramètres de validation
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
    """Charger les données enrichies avec périodes"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"✅ Données enrichies chargées: {len(data)} jours")
        return data
    except Exception as e:
        log(f"❌ Erreur chargement données: {e}")
        return None

def prepare_features_single(data, dates, target_idx):
    """
    Préparer les features avec périodes 3x8h pour prédire UN jour
    
    Features utilisées:
    - 7 derniers jours × (temp_avg + 3 périodes)
    - Variations entre périodes
    - Tendances pression
    - Saison
    """
    
    if target_idx < 7:
        return None, None, None
    
    target_date = dates[target_idx]
    
    # Features des 7 derniers jours
    features = []
    
    for j in range(1, 8):  # 7 derniers jours
        past_date = dates[target_idx - j]
        day_data = data[past_date]
        
        # Moyennes journalières
        features.append(day_data.get('temp_avg', 15))
        features.append(day_data.get('hum_avg', 70))
        features.append(day_data.get('pressure_avg', 1013))
        features.append(1 if day_data.get('rain', 0) > 0.5 else 0)
        
        # Périodes - ENRICHIES avec min/max/range
        for period in ['p1', 'p2', 'p3']:
            # Température période
            features.append(day_data.get(f'{period}_temp_avg', day_data.get('temp_avg', 15)))
            features.append(day_data.get(f'{period}_temp_min', day_data.get('temp_min', 10)))
            features.append(day_data.get(f'{period}_temp_max', day_data.get('temp_max', 20)))
            features.append(day_data.get(f'{period}_temp_range', 5))
            
            # Pression période
            features.append(day_data.get(f'{period}_pressure_avg', day_data.get('pressure_avg', 1013)))
            features.append(day_data.get(f'{period}_pressure_range', 5))
            
            # Humidité période
            features.append(day_data.get(f'{period}_hum_avg', day_data.get('hum_avg', 70)))
            features.append(day_data.get(f'{period}_hum_range', 10))
            
            # Vent période
            features.append(day_data.get(f'{period}_wind_max', 10))
            features.append(day_data.get(f'{period}_wind_range', 5))
            
            # Pluie période
            features.append(1 if day_data.get(f'{period}_has_rain', False) else 0)
    
    # Features d'hier (plus détaillées)
    yesterday = dates[target_idx - 1]
    yesterday_data = data[yesterday]
    
    # Variations classiques
    features.append(yesterday_data.get('temp_amplitude_day', 
                                      yesterday_data.get('temp_max', 20) - yesterday_data.get('temp_min', 10)))
    features.append(yesterday_data.get('pressure_drop_max', 5))
    features.append(yesterday_data.get('temp_p1_to_p2', 3))
    features.append(yesterday_data.get('temp_p2_to_p3', -2))
    features.append(yesterday_data.get('gust_max', 0))
    
    # Nouvelles features enrichies
    features.append(yesterday_data.get('temp_max_day', 20))  # Vrai pic de température
    features.append(yesterday_data.get('temp_min_day', 10))  # Vrai minimum
    features.append(yesterday_data.get('temp_total_range', 10))  # Somme des amplitudes
    features.append(yesterday_data.get('pressure_trend_day', 0))  # Tendance pression
    features.append(yesterday_data.get('pressure_total_range', 10))  # Instabilité pression
    features.append(yesterday_data.get('hum_range_day', 20))  # Variation humidité
    
    # Date features (saisonnalité)
    dt = datetime.strptime(target_date, '%Y-%m-%d')
    features.append(dt.timetuple().tm_yday)  # Jour de l'année
    features.append(dt.month)
    
    # Tendances sur 7 jours
    temps_7d = [data[dates[target_idx-j]].get('temp_avg', 15) for j in range(1, 8)]
    pressure_7d = [data[dates[target_idx-j]].get('pressure_avg', 1013) for j in range(1, 8)]
    
    features.append(np.mean(temps_7d[-3:]) - np.mean(temps_7d))  # Tendance température
    features.append(pressure_7d[0] - pressure_7d[-1])  # Tendance pression
    
    # Targets
    target_temp = data[target_date].get('temp_avg', 15)
    target_rain = 1 if data[target_date].get('rain', 0) > 0.5 else 0
    
    return np.array(features), target_temp, target_rain

def walk_forward_validation(data, dates):
    """Validation temporelle progressive"""
    
    log("=" * 70)
    log("🔄 WALK-FORWARD VALIDATION (avec périodes 3x8h)")
    log("=" * 70)
    
    results = {
        'predictions': [],
        'errors_temp': [],
        'errors_rain': []
    }
    
    total_days = len(dates)
    
    for day_idx in range(WALK_FORWARD_START, total_days):
        current_date = dates[day_idx]
        
        # 1. Préparer données d'entraînement
        X_temp_train = []
        y_temp_train = []
        X_rain_train = []
        y_rain_train = []
        
        for train_idx in range(7, day_idx):
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
        
        # 2. Entraîner
        model_temp = RandomForestRegressor(
            n_estimators=150,
            max_depth=12,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
        model_temp.fit(X_temp_train, y_temp_train)
        
        model_rain = RandomForestClassifier(
            n_estimators=150,
            max_depth=12,
            min_samples_split=5,
            random_state=42,
            n_jobs=-1
        )
        model_rain.fit(X_rain_train, y_rain_train)
        
        # 3. Prédire
        feat_test, temp_actual, rain_actual = prepare_features_single(data, dates, day_idx)
        
        if feat_test is None:
            continue
        
        temp_pred = model_temp.predict([feat_test])[0]
        rain_pred = model_rain.predict([feat_test])[0]
        rain_proba = model_rain.predict_proba([feat_test])[0][1] * 100
        
        # 4. Comparer
        temp_error = abs(temp_pred - temp_actual)
        rain_correct = 1 if rain_pred == rain_actual else 0
        
        # 5. Stocker
        results['predictions'].append({
            'date': current_date,
            'train_days': day_idx - 7,
            'temp_pred': round(temp_pred, 1),
            'temp_actual': round(temp_actual, 1),
            'temp_error': round(temp_error, 2),
            'rain_pred': bool(rain_pred),
            'rain_actual': bool(rain_actual),
            'rain_proba': round(rain_proba, 1),
            'rain_correct': bool(rain_correct)
        })
        
        results['errors_temp'].append(temp_error)
        results['errors_rain'].append(rain_correct)
        
        # Log progression
        if (day_idx - WALK_FORWARD_START) % 10 == 0:
            progress = ((day_idx - WALK_FORWARD_START) / (total_days - WALK_FORWARD_START)) * 100
            log(f"📊 Jour {day_idx}/{total_days} ({progress:.1f}%) - "
                f"MAE: {np.mean(results['errors_temp']):.2f}°C - "
                f"Acc: {np.mean(results['errors_rain'])*100:.1f}%")
    
    return results

def analyze_results(results):
    """Analyser les résultats"""
    
    log("\n" + "=" * 70)
    log("📈 ANALYSE DES RÉSULTATS")
    log("=" * 70)
    
    mae_temp = np.mean(results['errors_temp'])
    acc_rain = np.mean(results['errors_rain']) * 100
    
    log(f"\n📊 Performance Globale (avec périodes 3x8h):")
    log(f"   Température MAE: {mae_temp:.2f}°C")
    log(f"   Pluie Précision: {acc_rain:.1f}%")
    log(f"   Nombre de prédictions: {len(results['predictions'])}")
    
    # Évolution
    mid_point = len(results['errors_temp']) // 2
    
    mae_first = np.mean(results['errors_temp'][:mid_point])
    mae_second = np.mean(results['errors_temp'][mid_point:])
    
    acc_first = np.mean(results['errors_rain'][:mid_point]) * 100
    acc_second = np.mean(results['errors_rain'][mid_point:]) * 100
    
    log(f"\n📈 Évolution:")
    log(f"   Température - Début: {mae_first:.2f}°C, Fin: {mae_second:.2f}°C")
    log(f"   Pluie - Début: {acc_first:.1f}%, Fin: {acc_second:.1f}%")
    
    improvement_temp = ((mae_first - mae_second) / mae_first) * 100
    improvement_rain = acc_second - acc_first
    
    if improvement_temp > 0:
        log(f"   ✅ Amélioration température: {improvement_temp:.1f}%")
    else:
        log(f"   ⚠️ Dégradation température: {abs(improvement_temp):.1f}%")
    
    if improvement_rain > 0:
        log(f"   ✅ Amélioration pluie: +{improvement_rain:.1f}%")
    
    # Pires prédictions
    log(f"\n❌ 5 Pires Prédictions:")
    sorted_preds = sorted(results['predictions'], key=lambda x: x['temp_error'], reverse=True)
    for pred in sorted_preds[:5]:
        log(f"   {pred['date']}: Prédit {pred['temp_pred']}°C, Réel {pred['temp_actual']}°C, "
            f"Erreur {pred['temp_error']}°C")
    
    return mae_temp, acc_rain

def train_final_model(data, dates):
    """Entraîner le modèle final sur toutes les données"""
    
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
    
    log(f"   {len(X_temp)} échantillons, {X_temp.shape[1]} features par échantillon")
    
    # Entraîner avec plus d'arbres pour le modèle final
    model_temp = RandomForestRegressor(
        n_estimators=200,
        max_depth=12,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1
    )
    model_temp.fit(X_temp, y_temp)
    
    model_rain = RandomForestClassifier(
        n_estimators=200,
        max_depth=12,
        min_samples_split=5,
        random_state=42,
        n_jobs=-1
    )
    model_rain.fit(X_rain, y_rain)
    
    # Sauvegarder
    joblib.dump(model_temp, f"{MODEL_DIR}/model_temp_3x8h.pkl")
    joblib.dump(model_rain, f"{MODEL_DIR}/model_rain_3x8h.pkl")
    
    log("   ✅ Modèles 3x8h sauvegardés")
    
    return model_temp, model_rain

def save_results(results, mae_temp, acc_rain):
    """Sauvegarder les résultats"""
    
    output = {
        'validation_date': datetime.now().isoformat(),
        'model_type': '3x8h_periods',
        'metrics': {
            'temperature_mae': float(mae_temp),
            'rain_accuracy': float(acc_rain / 100),
            'predictions_count': len(results['predictions'])
        },
        'all_predictions': results['predictions']
    }
    
    with open(f"{MODEL_DIR}/validation_results_3x8h.json", 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    metrics = {
        'trained_at': datetime.now().isoformat(),
        'model_type': '3x8h_periods',
        'temp_mae': float(mae_temp),
        'rain_accuracy': float(acc_rain / 100)
    }
    
    with open(f"{MODEL_DIR}/metrics_3x8h.json", 'w', encoding='utf-8') as f:
        json.dump(metrics, f, indent=2)
    
    log(f"\n💾 Résultats sauvegardés")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🤖 ENTRAÎNEMENT AVEC PÉRIODES 3x8h + WALK-FORWARD")
    log("=" * 70)
    
    # 1. Charger
    data = load_data()
    if not data or len(data) < MIN_TRAIN_DAYS:
        log(f"❌ Pas assez de données (minimum {MIN_TRAIN_DAYS} jours)")
        return
    
    dates = sorted(data.keys())
    log(f"📅 Période: {dates[0]} → {dates[-1]}")
    log(f"📊 {len(dates)} jours disponibles")
    
    # 2. Validation
    results = walk_forward_validation(data, dates)
    
    # 3. Analyser
    mae_temp, acc_rain = analyze_results(results)
    
    # 4. Modèle final
    model_temp, model_rain = train_final_model(data, dates)
    
    # 5. Sauvegarder
    save_results(results, mae_temp, acc_rain)
    
    log("\n" + "=" * 70)
    log("✅ ENTRAÎNEMENT 3x8h TERMINÉ")
    log("=" * 70)
    log(f"📊 Température MAE: ±{mae_temp:.2f}°C")
    log(f"📊 Pluie Précision: {acc_rain:.1f}%")
    log("=" * 70)

if __name__ == "__main__":
    main()
