#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de génération de prévisions avec modèle MULTI-HORIZONS - VERSION CORRIGÉE
Prédit AUJOURD'HUI, DEMAIN, APRÈS-DEMAIN avec prédictions SÉQUENTIELLES
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
import joblib

# ============================================
# CONFIGURATION
# ============================================

# Chemins — relatifs à la racine du repo
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE   = os.path.join(BASE_DIR, "data", "meteo_data_enriched.json")
MODEL_DIR   = os.path.join(BASE_DIR, "data", "models")
OUTPUT_FILE = os.path.join(BASE_DIR, "data", "predictions.json")
LOG_FILE    = os.path.join(BASE_DIR, "logs", "predictions_multihorizon.log")

# FTP — credentials via variables d'environnement (GitHub Secrets)
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
FTP_PATH = ""

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

def load_models():
    """Charger les modèles multi-horizons"""
    try:
        model_temp = joblib.load(f"{MODEL_DIR}/model_temp_multihorizon.pkl")
        model_rain = joblib.load(f"{MODEL_DIR}/model_rain_multihorizon.pkl")
        
        with open(f"{MODEL_DIR}/metrics_multihorizon.json", 'r') as f:
            metrics = json.load(f)
        
        log("✅ Modèles multi-horizons chargés")
        return model_temp, model_rain, metrics
    except Exception as e:
        log(f"❌ Erreur chargement modèles: {e}")
        return None, None, None

def load_data():
    """Charger les données enrichies"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        log(f"✅ Données chargées: {len(data)} jours")
        return data
    except Exception as e:
        log(f"❌ Erreur chargement données: {e}")
        return None

def prepare_features_for_horizon(data, dates, horizon, previous_predictions=None):
    """
    Préparer les features pour un horizon donné - VERSION CORRIGÉE
    
    Args:
        data: Données météo
        dates: Liste des dates triées
        horizon: 0=aujourd'hui, 1=demain, 2=après-demain
        previous_predictions: Dict avec prédictions précédentes
    
    CORRECTION : Utilise les prédictions précédentes pour H > 0
    """
    
    last_idx = len(dates) - 1
    
    # Vérifier l'historique minimum
    if last_idx < 7:
        return None, None
    
    features = []
    
    # ========================================================================
    # CORRECTION : Historique différent selon l'horizon
    # ========================================================================
    
    if horizon == 0:
        # AUJOURD'HUI : 7 derniers jours réels
        num_real_days = 7
        history_days = [last_idx - j for j in range(1, num_real_days + 1)]
        
    elif horizon == 1:
        # DEMAIN : 6 jours réels + prédiction aujourd'hui
        num_real_days = 6
        history_days = [last_idx - j for j in range(1, num_real_days + 1)]
        
    else:  # horizon == 2
        # APRÈS-DEMAIN : 5 jours réels + prédictions aujourd'hui et demain
        num_real_days = 5
        history_days = [last_idx - j for j in range(1, num_real_days + 1)]
    
    # ========================================================================
    # Features des jours RÉELS
    # ========================================================================
    
    for day_idx in history_days:
        if day_idx < 0:
            return None, None
            
        past_date = dates[day_idx]
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
    
    # ========================================================================
    # CORRECTION : Ajouter les prédictions précédentes
    # ========================================================================
    
    if horizon == 1 and previous_predictions and 0 in previous_predictions:
        # Pour DEMAIN : ajouter prédiction AUJOURD'HUI
        pred_h0 = previous_predictions[0]
        
        # Simuler un jour avec la prédiction
        features.append(pred_h0['temp_pred'])
        features.append(70)
        features.append(1013)
        features.append(1 if pred_h0['rain_pred'] else 0)
        
        # Périodes
        for period_key in ['p1', 'p2', 'p3']:
            period_temp = pred_h0['period_temps'][period_key]
            features.append(period_temp)
            features.append(period_temp - 2)
            features.append(period_temp + 2)
            features.append(4)
            features.append(1013)
            features.append(5)
            features.append(70)
            features.append(10)
            features.append(10)
            features.append(5)
            features.append(1 if pred_h0['rain_pred'] else 0)
    
    elif horizon == 2 and previous_predictions:
        # Pour APRÈS-DEMAIN : ajouter prédictions AUJOURD'HUI et DEMAIN
        for h in [0, 1]:
            if h in previous_predictions:
                pred = previous_predictions[h]
                
                features.append(pred['temp_pred'])
                features.append(70)
                features.append(1013)
                features.append(1 if pred['rain_pred'] else 0)
                
                for period_key in ['p1', 'p2', 'p3']:
                    period_temp = pred['period_temps'][period_key]
                    features.append(period_temp)
                    features.append(period_temp - 2)
                    features.append(period_temp + 2)
                    features.append(4)
                    features.append(1013)
                    features.append(5)
                    features.append(70)
                    features.append(10)
                    features.append(10)
                    features.append(5)
                    features.append(1 if pred['rain_pred'] else 0)
    
    # ========================================================================
    # Features du dernier jour RÉEL connu
    # ========================================================================
    
    yesterday_idx = last_idx - 1
    if yesterday_idx < 0:
        return None, None
        
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
    
    # ========================================================================
    # Date cible (DIFFÉRENTE pour chaque horizon)
    # ========================================================================
    
    target_date = datetime.now() + timedelta(days=horizon)
    features.append(target_date.timetuple().tm_yday)
    features.append(target_date.month)
    
    # Horizon
    features.append(horizon)
    
    # Tendances sur les jours RÉELS
    temps_7d = [data[dates[last_idx - j]].get('temp_avg', 15) for j in range(1, min(8, last_idx + 1))]
    pressure_7d = [data[dates[last_idx - j]].get('pressure_avg', 1013) for j in range(1, min(8, last_idx + 1))]
    
    if len(temps_7d) >= 3:
        features.append(np.mean(temps_7d[:3]) - np.mean(temps_7d))
    else:
        features.append(0)
    
    if len(pressure_7d) >= 2:
        features.append(pressure_7d[0] - pressure_7d[-1])
    else:
        features.append(0)
    
    log(f"   📊 Features H={horizon}: {len(features)} éléments")
    
    return np.array([features]), target_date

def estimate_period_temps(temp_pred, horizon, data, dates):
    """Estimer températures par période"""
    
    recent_p2_max = []
    recent_p1_min = []
    
    for j in range(1, 8):
        idx = len(dates) - j
        if idx >= 0:
            day = data[dates[idx]]
            if day.get('p2_temp_max') is not None:
                recent_p2_max.append(day['p2_temp_max'])
            if day.get('p1_temp_min') is not None:
                recent_p1_min.append(day['p1_temp_min'])
    
    if recent_p2_max and recent_p1_min:
        typical_amplitude = np.mean([p2 - p1 for p2, p1 in zip(recent_p2_max[:3], recent_p1_min[:3])])
    else:
        typical_amplitude = 8.0
    
    # Ajuster selon l'horizon
    amplitude_factors = [0.5, 0.45, 0.4]
    morning_factors = [-0.3, -0.25, -0.2]
    night_factors = [-0.2, -0.15, -0.1]
    
    return {
        'p1': round(temp_pred + typical_amplitude * morning_factors[horizon], 1),
        'p2': round(temp_pred + typical_amplitude * amplitude_factors[horizon], 1),
        'p3': round(temp_pred + typical_amplitude * night_factors[horizon], 1)
    }

def generate_predictions(model_temp, model_rain, metrics, data):
    """Générer prévisions pour 3 horizons - VERSION CORRIGÉE"""
    
    log("🔧 Génération prévisions multi-horizons (SÉQUENTIEL)...")
    
    dates = sorted(data.keys())
    log(f"   📊 {len(dates)} jours disponibles")
    log(f"   📅 Dernier jour: {dates[-1]}")
    
    forecasts = []
    previous_predictions = {}
    
    for horizon in [0, 1, 2]:
        label = ["Aujourd'hui", "Demain", "Après-demain"][horizon]
        
        if horizon == 0:
            log(f"\n   📅 {label} (H=0)...")
        elif horizon == 1:
            log(f"\n   📅 {label} (H=1) - utilise prédiction H=0...")
        else:
            log(f"\n   📅 {label} (H=2) - utilise prédictions H=0 et H=1...")
        
        features, target_date = prepare_features_for_horizon(
            data, dates, horizon, previous_predictions
        )
        
        if features is None:
            log(f"   ❌ Erreur pour H={horizon}")
            continue
        
        temp_pred = model_temp.predict(features)[0]
        rain_pred = model_rain.predict(features)[0]
        rain_proba = model_rain.predict_proba(features)[0]
        rain_prob = rain_proba[1] * 100
        
        base_conf = (1 - metrics['temp_mae'] / 10) * 100
        conf_factors = [1.0, 0.90, 0.75]
        confidence = min(max(base_conf * conf_factors[horizon], 50), 95)
        
        temp_margin = metrics['temp_mae'] * (1.0 + 0.3 * horizon)
        
        period_temps = estimate_period_temps(temp_pred, horizon, data, dates)
        
        previous_predictions[horizon] = {
            'temp_pred': temp_pred,
            'rain_pred': rain_pred,
            'period_temps': period_temps
        }
        
        rain_risk = 'low' if rain_prob < 30 else ('medium' if rain_prob < 60 else 'high')
        
        forecast = {
            'date': target_date.strftime('%Y-%m-%d'),
            'day_name': target_date.strftime('%A'),
            'day_number': horizon,
            'day_label': label,
            'temperature': {
                'predicted': round(temp_pred, 1),
                'min_estimate': round(temp_pred - temp_margin, 1),
                'max_estimate': round(temp_pred + temp_margin, 1)
            },
            'rain': {
                'will_rain': bool(rain_pred),
                'probability': round(rain_prob, 0)
            },
            'confidence': round(confidence, 0),
            'periods': {
                'p1': {'name': 'Matin (04h-12h)', 'temp_estimate': period_temps['p1'], 'rain_risk': rain_risk},
                'p2': {'name': 'Après-midi (12h-20h)', 'temp_estimate': period_temps['p2'], 'rain_risk': rain_risk},
                'p3': {'name': 'Nuit (20h-04h)', 'temp_estimate': period_temps['p3'], 'rain_risk': rain_risk}
            }
        }
        
        forecasts.append(forecast)
        
        p1 = period_temps['p1']
        p2 = period_temps['p2']
        p3 = period_temps['p3']
        log(f"   ✅ {label}: {temp_pred:.1f}°C (P1:{p1}° P2:{p2}° P3:{p3}°)")
        log(f"      Pluie: {rain_prob:.0f}%, Confiance: {confidence:.0f}%")
    
    predictions = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics.get('trained_at', 'unknown'),
        'model_type': 'multihorizon_sequential',
        'forecasts': forecasts,
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae']:.1f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%"
        }
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)
    
    log(f"\n✅ Prévisions sauvegardées: {OUTPUT_FILE}")
    
    return predictions

def upload_to_server():
    """Upload FTP"""
    try:
        import ftplib
        
        log("\n📤 Connexion FTP...")
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        
        if FTP_PATH:
            ftp.cwd(FTP_PATH)
        
        log(f"📤 Upload predictions.json...")
        with open(OUTPUT_FILE, 'rb') as f:
            ftp.storbinary('STOR predictions.json', f)
        
        ftp.quit()
        log("✅ Upload FTP réussi")
        
    except Exception as e:
        log(f"❌ Erreur FTP: {e}")

def main():
    log("=" * 70)
    log("🔮 PRÉVISIONS MULTI-HORIZONS - VERSION CORRIGÉE")
    log("=" * 70)
    
    model_temp, model_rain, metrics = load_models()
    if not model_temp:
        log("❌ Impossible de charger les modèles")
        return
    
    data = load_data()
    if not data:
        log("❌ Impossible de charger les données")
        return
    
    predictions = generate_predictions(model_temp, model_rain, metrics, data)
    
    upload_to_server()
    
    log("")
    log("=" * 70)
    log("✅ PRÉVISIONS GÉNÉRÉES (SÉQUENTIELLES)")
    log("=" * 70)
    
    for forecast in predictions['forecasts']:
        label = forecast['day_label']
        date = forecast['date']
        temp = forecast['temperature']['predicted']
        p1 = forecast['periods']['p1']['temp_estimate']
        p2 = forecast['periods']['p2']['temp_estimate']
        p3 = forecast['periods']['p3']['temp_estimate']
        rain = forecast['rain']['probability']
        conf = forecast['confidence']
        
        log(f"\n📅 {label} ({date}):")
        log(f"   🌡️  Température: {temp}°C")
        log(f"   ⏰ Matin: {p1}°C | Après-midi: {p2}°C | Nuit: {p3}°C")
        log(f"   🌧️  Pluie: {rain:.0f}%")
        log(f"   📊 Confiance: {conf:.0f}%")
    
    log("\n" + "=" * 70)

if __name__ == "__main__":
    main()
