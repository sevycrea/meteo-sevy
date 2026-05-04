#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de génération de prévisions 3 JOURS avec modèle 3x8h
Prédit J+1, J+2, J+3 avec détails par période
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
import joblib

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Documents/Météo"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_FILE = f"{BASE_DIR}/data/json/predictions.json"
LOG_FILE = f"{BASE_DIR}/logs/predictions_3days.log"

# FTP Upload (configuration Infomaniak)
FTP_HOST = "ig6i34.ftp.infomaniak.com"
FTP_USER = "ig6i34_data_net"
FTP_PASS = "Cf301164!222"  # ⚠️ À REMPLACER
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
    """Charger les modèles 3x8h entraînés"""
    try:
        model_temp = joblib.load(f"{MODEL_DIR}/model_temp_3x8h.pkl")
        model_rain = joblib.load(f"{MODEL_DIR}/model_rain_3x8h.pkl")
        
        with open(f"{MODEL_DIR}/metrics_3x8h.json", 'r') as f:
            metrics = json.load(f)
        
        log("✅ Modèles 3x8h chargés")
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

def prepare_features_for_day(data, dates, days_ahead):
    """
    Préparer les features pour prédire un jour spécifique
    
    Args:
        data: Données complètes
        dates: Liste des dates triées
        days_ahead: 0=aujourd'hui, 1=demain, 2=après-demain
    """
    
    features = []
    
    # Le dernier jour avec des données complètes
    last_complete_day_idx = len(dates) - 1
    
    # Pour prédire J+N, on utilise les données jusqu'à aujourd'hui (dernier jour connu)
    # et on regarde 7 jours en arrière depuis aujourd'hui
    
    # Vérifier qu'on a assez d'historique (7 jours)
    if last_complete_day_idx < 6:  # On a besoin d'au moins 7 jours
        return None, None
    
    # Features des 7 derniers jours disponibles
    for offset in range(0, 7):  # De 0 à 6 (aujourd'hui et les 6 jours précédents)
        past_idx = last_complete_day_idx - offset
        
        if past_idx < 0:
            return None, None
        
        past_date = dates[past_idx]
        day_data = data[past_date]
        
        # Moyennes journalières
        features.append(day_data.get('temp_avg', 15))
        features.append(day_data.get('hum_avg', 70))
        features.append(day_data.get('pressure_avg', 1013))
        features.append(1 if day_data.get('rain', 0) > 0.5 else 0)
        
        # Périodes - ENRICHIES avec min/max/range
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
    
    # Features du dernier jour connu (hier pour prédire aujourd'hui, aujourd'hui pour prédire demain)
    yesterday = dates[last_complete_day_idx]
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
    
    # Date du jour à prédire
    target_date = datetime.now() + timedelta(days=days_ahead)
    features.append(target_date.timetuple().tm_yday)
    features.append(target_date.month)
    
    # Tendances sur les 7 derniers jours
    temps_7d = [data[dates[last_complete_day_idx - i]].get('temp_avg', 15) for i in range(7)]
    pressure_7d = [data[dates[last_complete_day_idx - i]].get('pressure_avg', 1013) for i in range(7)]
    
    features.append(np.mean(temps_7d[:3]) - np.mean(temps_7d))
    features.append(pressure_7d[0] - pressure_7d[-1])
    
    # Vérifier le nombre de features
    total_features = len(features)
    # log(f"   📊 Features générées: {total_features}")
    
    return np.array([features]), target_date

def predict_day(model_temp, model_rain, features):
    """Générer les prévisions pour un jour"""
    
    temp_pred = model_temp.predict(features)[0]
    rain_pred = model_rain.predict(features)[0]
    rain_proba = model_rain.predict_proba(features)[0]
    rain_prob = rain_proba[1] * 100
    
    return temp_pred, rain_pred, rain_prob

def calculate_confidence(metrics, days_ahead):
    """
    Calculer le niveau de confiance selon le nombre de jours
    La confiance diminue avec la distance
    """
    
    base_confidence = (1 - metrics['temp_mae'] / 10) * 100
    
    # Réduction selon le jour
    if days_ahead == 1:
        confidence_factor = 1.0
    elif days_ahead == 2:
        confidence_factor = 0.85
    else:  # jour 3
        confidence_factor = 0.70
    
    confidence = base_confidence * confidence_factor
    
    return min(max(confidence, 50), 95)

def estimate_period_temps(temp_pred, days_ahead, data, dates):
    """
    Estimer les températures par période en se basant sur les patterns historiques
    Utilise les vraies amplitudes observées
    """
    
    # Analyser les 7 derniers jours pour voir l'amplitude typique
    recent_p2_max = []
    recent_p1_min = []
    recent_p3_avg = []
    
    for j in range(1, 8):
        idx = len(dates) - j
        if idx >= 0:
            day = data[dates[idx]]
            if day.get('p2_temp_max') is not None:
                recent_p2_max.append(day['p2_temp_max'])
            if day.get('p1_temp_min') is not None:
                recent_p1_min.append(day['p1_temp_min'])
            if day.get('p3_temp_avg') is not None:
                recent_p3_avg.append(day['p3_temp_avg'])
    
    # Calculer les écarts typiques
    if recent_p2_max and recent_p1_min:
        typical_morning_to_afternoon = np.mean([p2 - p1 for p2, p1 in zip(recent_p2_max[:3], recent_p1_min[:3])])
    else:
        typical_morning_to_afternoon = 8.0  # Par défaut
    
    # Ajuster selon le jour (plus d'incertitude = plus conservateur)
    if days_ahead == 1:
        afternoon_adj = typical_morning_to_afternoon * 0.5  # Utilise la vraie amplitude
        morning_adj = -typical_morning_to_afternoon * 0.3
        night_adj = -typical_morning_to_afternoon * 0.2
    elif days_ahead == 2:
        afternoon_adj = typical_morning_to_afternoon * 0.4
        morning_adj = -typical_morning_to_afternoon * 0.25
        night_adj = -typical_morning_to_afternoon * 0.15
    else:  # jour 3
        afternoon_adj = typical_morning_to_afternoon * 0.3
        morning_adj = -typical_morning_to_afternoon * 0.2
        night_adj = -typical_morning_to_afternoon * 0.1
    
    return {
        'p1': round(temp_pred + morning_adj, 1),
        'p2': round(temp_pred + afternoon_adj, 1),  # LE VRAI MAX
        'p3': round(temp_pred + night_adj, 1)
    }

def generate_predictions_3days(model_temp, model_rain, metrics, data):
    """Générer les prévisions : Aujourd'hui + 2 prochains jours"""
    
    log("🔧 Génération des prévisions : Aujourd'hui, Demain, Après-demain...")
    
    dates = sorted(data.keys())
    log(f"   📊 Nombre total de jours disponibles: {len(dates)}")
    log(f"   📅 Dernier jour connu: {dates[-1]}")
    
    forecasts = []
    
    # AUJOURD'HUI (J+0), DEMAIN (J+1), APRÈS-DEMAIN (J+2)
    for day in range(0, 3):
        if day == 0:
            log(f"   📅 Aujourd'hui (J+0)...")
        elif day == 1:
            log(f"   📅 Demain (J+1)...")
        else:
            log(f"   📅 Après-demain (J+2)...")
        
        features, target_date = prepare_features_for_day(data, dates, day)
        
        if features is None:
            log(f"   ❌ Pas assez de données pour J+{day}")
            log(f"      Dates disponibles: {len(dates)}")
            log(f"      Days ahead: {day}")
            continue
        
        temp_pred, rain_pred, rain_prob = predict_day(model_temp, model_rain, features)
        confidence = calculate_confidence(metrics, day)
        
        # Marge d'erreur augmente avec les jours
        temp_margin = metrics['temp_mae'] * (1.0 + 0.3 * day)
        
        # Températures par période
        period_temps = estimate_period_temps(temp_pred, day, data, dates)
        
        # Déterminer le risque de pluie par période
        if rain_prob < 30:
            rain_risk = 'low'
        elif rain_prob < 60:
            rain_risk = 'medium'
        else:
            rain_risk = 'high'
        
        # Nom du jour
        if day == 0:
            day_label = "Aujourd'hui"
        elif day == 1:
            day_label = "Demain"
        else:
            day_label = "Après-demain"
        
        forecast = {
            'date': target_date.strftime('%Y-%m-%d'),
            'day_name': target_date.strftime('%A'),
            'day_number': day,
            'day_label': day_label,
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
                'p1': {
                    'name': 'Matin (04h-12h)',
                    'temp_estimate': period_temps['p1'],
                    'rain_risk': rain_risk
                },
                'p2': {
                    'name': 'Après-midi (12h-20h)',
                    'temp_estimate': period_temps['p2'],
                    'rain_risk': rain_risk
                },
                'p3': {
                    'name': 'Nuit (20h-04h)',
                    'temp_estimate': period_temps['p3'],
                    'rain_risk': rain_risk
                }
            }
        }
        
        forecasts.append(forecast)
        
        log(f"   ✅ {day_label}: {temp_pred:.1f}°C, Pluie {rain_prob:.0f}%, Confiance {confidence:.0f}%")
    
    # Structure de sortie
    predictions = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics.get('trained_at', 'unknown'),
        'model_type': '3x8h_periods',
        'forecasts': forecasts,
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae']:.1f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%"
        }
    }
    
    # Sauvegarder
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)
    
    log(f"✅ Prévisions 3 jours sauvegardées: {OUTPUT_FILE}")
    
    return predictions

def upload_to_server():
    """Uploader via FTP"""
    
    if FTP_PASS == "VOTRE_MOT_DE_PASSE_ICI":
        log("⚠️  FTP non configuré - upload ignoré")
        return
    
    try:
        import ftplib
        
        log("📤 Connexion FTP...")
        log(f"   Serveur: {FTP_HOST}")
        log(f"   User: {FTP_USER}")
        
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        
        log(f"✅ Connecté - changement de répertoire...")
        ftp.cwd(FTP_PATH)
        
        log(f"📤 Upload de predictions.json...")
        with open(OUTPUT_FILE, 'rb') as f:
            ftp.storbinary('STOR predictions.json', f)
        
        ftp.quit()
        log("✅ Upload FTP réussi")
        
    except Exception as e:
        log(f"❌ Erreur FTP: {e}")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🔮 GÉNÉRATION PRÉVISIONS MÉTÉO 3 JOURS (Modèle 3x8h)")
    log("=" * 70)
    
    # 1. Charger modèles
    model_temp, model_rain, metrics = load_models()
    if not model_temp:
        log("❌ Impossible de charger les modèles")
        return
    
    # 2. Charger données
    data = load_data()
    if not data:
        log("❌ Impossible de charger les données")
        return
    
    # 3. Générer prévisions 3 jours
    predictions = generate_predictions_3days(model_temp, model_rain, metrics, data)
    
    # 4. Upload FTP
    upload_to_server()
    
    # 5. Résumé
    log("")
    log("=" * 70)
    log("✅ PRÉVISIONS GÉNÉRÉES : AUJOURD'HUI + 2 JOURS")
    log("=" * 70)
    
    for forecast in predictions['forecasts']:
        day_label = forecast['day_label']
        date = forecast['date']
        temp = forecast['temperature']['predicted']
        temp_range = f"{forecast['temperature']['min_estimate']}°C - {forecast['temperature']['max_estimate']}°C"
        rain = forecast['rain']['probability']
        conf = forecast['confidence']
        
        log(f"📅 {day_label} ({date}):")
        log(f"   🌡️ Température: {temp}°C ({temp_range})")
        log(f"   🌧️ Pluie: {rain:.0f}%")
        log(f"   📊 Confiance: {conf:.0f}%")
    
    log("=" * 70)

if __name__ == "__main__":
    main()
