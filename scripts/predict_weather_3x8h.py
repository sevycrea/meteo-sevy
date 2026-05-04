!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de génération de prévisions avec modèle 3x8h
Prédit la météo de demain avec détails par période
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
import joblib

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_FILE = f"{BASE_DIR}/data/json/predictions.json"
LOG_FILE = f"{BASE_DIR}/logs/predictions_3x8h.log"

# FTP Upload (configuration Infomaniak)
FTP_HOST = "ig6i34.ftp.infomaniak.com"
FTP_USER = "ig6i34_data_net"
FTP_PASS = "301164!222"  # ⚠️ À REMPLACER
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
        
        # Charger les métriques
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

def prepare_features_for_tomorrow(data):
    """Préparer les features pour prédire demain"""
    
    dates = sorted(data.keys())
    
    # Features des 7 derniers jours
    features = []
    
    for j in range(1, 8):
        past_date = dates[-j]
        day_data = data[past_date]
        
        # Moyennes journalières
        features.append(day_data.get('temp_avg', 15))
        features.append(day_data.get('hum_avg', 70))
        features.append(day_data.get('pressure_avg', 1013))
        features.append(1 if day_data.get('rain', 0) > 0.5 else 0)
        
        # Périodes
        for period in ['p1', 'p2', 'p3']:
            features.append(day_data.get(f'{period}_temp_avg', day_data.get('temp_avg', 15)))
            features.append(day_data.get(f'{period}_pressure_avg', day_data.get('pressure_avg', 1013)))
            features.append(1 if day_data.get(f'{period}_has_rain', False) else 0)
    
    # Features d'hier
    yesterday = dates[-1]
    yesterday_data = data[yesterday]
    
    features.append(yesterday_data.get('temp_amplitude_day', 
                                      yesterday_data.get('temp_max', 20) - yesterday_data.get('temp_min', 10)))
    features.append(yesterday_data.get('pressure_drop_max', 5))
    features.append(yesterday_data.get('temp_p1_to_p2', 3))
    features.append(yesterday_data.get('temp_p2_to_p3', -2))
    features.append(yesterday_data.get('gust_max', 0))
    
    # Date de demain
    tomorrow = datetime.now() + timedelta(days=1)
    features.append(tomorrow.timetuple().tm_yday)
    features.append(tomorrow.month)
    
    # Tendances
    temps_7d = [data[dates[-j]].get('temp_avg', 15) for j in range(1, 8)]
    pressure_7d = [data[dates[-j]].get('pressure_avg', 1013) for j in range(1, 8)]
    
    features.append(np.mean(temps_7d[-3:]) - np.mean(temps_7d))
    features.append(pressure_7d[0] - pressure_7d[-1])
    
    return np.array([features]), tomorrow

def predict_tomorrow(model_temp, model_rain, features):
    """Générer les prévisions"""
    
    # Température
    temp_pred = model_temp.predict(features)[0]
    
    # Pluie
    rain_pred = model_rain.predict(features)[0]
    rain_proba = model_rain.predict_proba(features)[0]
    rain_prob = rain_proba[1] * 100
    
    return temp_pred, rain_pred, rain_prob

def calculate_confidence(metrics, recent_data):
    """Calculer le niveau de confiance"""
    
    # Confiance de base du modèle
    base_confidence = (1 - metrics['temp_mae'] / 10) * 100  # Ex: 1.5°C MAE = 85%
    
    # Ajuster selon stabilité récente
    last_7_temps = [day.get('temp_avg', 15) for day in list(recent_data.values())[-7:]]
    stability = 1 - (np.std(last_7_temps) / 10)  # Moins de variation = plus stable
    
    confidence = base_confidence * (0.7 + 0.3 * stability)
    
    return min(max(confidence, 50), 95)  # Entre 50% et 95%

def generate_predictions(model_temp, model_rain, metrics, data):
    """Générer le fichier de prévisions"""
    
    log("🔧 Préparation des features...")
    features, tomorrow = prepare_features_for_tomorrow(data)
    
    log("🤖 Génération des prévisions...")
    temp_pred, rain_pred, rain_prob = predict_tomorrow(model_temp, model_rain, features)
    
    # Confiance
    confidence = calculate_confidence(metrics, data)
    
    # Marge d'erreur
    temp_margin = metrics['temp_mae'] * 1.5
    
    # Structure de sortie
    predictions = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics.get('trained_at', 'unknown'),
        'model_type': '3x8h_periods',
        'tomorrow': {
            'date': tomorrow.strftime('%Y-%m-%d'),
            'day_name': tomorrow.strftime('%A'),
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
                    'temp_estimate': round(temp_pred - 2, 1),  # Plus frais le matin
                    'rain_risk': 'low' if rain_prob < 30 else ('medium' if rain_prob < 60 else 'high')
                },
                'p2': {
                    'name': 'Après-midi (12h-20h)',
                    'temp_estimate': round(temp_pred + 2, 1),  # Plus chaud l'après-midi
                    'rain_risk': 'low' if rain_prob < 30 else ('medium' if rain_prob < 60 else 'high')
                },
                'p3': {
                    'name': 'Nuit (20h-04h)',
                    'temp_estimate': round(temp_pred - 1, 1),  # Intermédiaire
                    'rain_risk': 'low' if rain_prob < 30 else ('medium' if rain_prob < 60 else 'high')
                }
            }
        },
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae']:.1f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%"
        }
    }
    
    # Sauvegarder
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)
    
    log(f"✅ Prévisions sauvegardées: {OUTPUT_FILE}")
    
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
    log("🔮 GÉNÉRATION PRÉVISIONS MÉTÉO (Modèle 3x8h)")
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
    
    # 3. Générer prévisions
    predictions = generate_predictions(model_temp, model_rain, metrics, data)
    
    # 4. Upload FTP
    upload_to_server()
    
    # 5. Résumé
    log("")
    log("=" * 70)
    log(f"✅ PRÉVISIONS POUR DEMAIN ({predictions['tomorrow']['date']})")
    log("=" * 70)
    log(f"   🌡️ Température: {predictions['tomorrow']['temperature']['predicted']}°C "
        f"({predictions['tomorrow']['temperature']['min_estimate']}°C - "
        f"{predictions['tomorrow']['temperature']['max_estimate']}°C)")
    log(f"   🌧️ Pluie: {predictions['tomorrow']['rain']['probability']:.0f}% de probabilité")
    log(f"   📊 Confiance: {predictions['tomorrow']['confidence']:.0f}%")
    log("")
    log("   Détails par période:")
    for period_key, period_data in predictions['tomorrow']['periods'].items():
        log(f"      {period_data['name']}: {period_data['temp_estimate']}°C, "
            f"Risque pluie: {period_data['rain_risk']}")
    log("=" * 70)

if __name__ == "__main__":
    main()
