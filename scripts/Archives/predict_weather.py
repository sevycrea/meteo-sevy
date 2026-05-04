#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de génération des prévisions météo
Utilise les modèles entraînés pour prédire le temps de demain
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
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_FILE = f"{BASE_DIR}/data/json/predictions.json"
LOG_FILE = f"{BASE_DIR}/logs/predictions.log"

# FTP Upload (configuration Infomaniak)
FTP_HOST = "ig6i34.ftp.infomaniak.com"
FTP_USER = "ig6i34_data_net"
FTP_PASS = "Cf301164!222"  # ⚠️ À REMPLACER par votre mot de passe
FTP_PATH = ""  #

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Écrire dans le fichier log"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message)

def load_models():
    """Charger les modèles entraînés"""
    try:
        model_temp = joblib.load(f"{MODEL_DIR}/model_temp.pkl")
        model_rain = joblib.load(f"{MODEL_DIR}/model_rain.pkl")
        
        with open(f"{MODEL_DIR}/metrics.json", 'r') as f:
            metrics = json.load(f)
        
        log(f"✅ Modèles chargés (entraînés le {metrics['trained_at'][:10]})")
        return model_temp, model_rain, metrics
    except Exception as e:
        log(f"❌ Erreur chargement modèles: {e}")
        return None, None, None

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

def prepare_features_for_tomorrow(data):
    """
    Préparer les features pour prédire demain
    Utilise les 7 derniers jours de données
    """
    
    dates = sorted(data.keys())
    last_7_dates = dates[-7:]
    yesterday = dates[-1]
    
    # Features des 7 derniers jours
    temps_7d = [data[date]['temp_avg'] for date in last_7_dates]
    hum_7d = [data[date].get('hum_avg', 70) for date in last_7_dates]
    pressure_7d = [data[date].get('pressure_avg', 1013) for date in last_7_dates]
    rain_7d = [1 if data[date].get('rain', 0) > 0 else 0 for date in last_7_dates]
    
    # Ajouter les variations (comme dans le modèle)
    temp_range = data[yesterday]['temp_max'] - data[yesterday]['temp_min']
    hum_range = data[yesterday].get('hum_max', 100) - data[yesterday].get('hum_min', 0)
    pressure_range = data[yesterday].get('pressure_max', 1030) - data[yesterday].get('pressure_min', 990)
    gust_max_yesterday = data[yesterday].get('gust_max', 0)
    
    # Date features pour demain
    tomorrow = datetime.now() + timedelta(days=1)
    day_of_year = tomorrow.timetuple().tm_yday
    month = tomorrow.month
    
    # Tendances
    temp_trend = np.mean(temps_7d[-3:]) - np.mean(temps_7d)
    pressure_trend = pressure_7d[-1] - pressure_7d[0]
    
    # Features combinées (MÊME STRUCTURE que l'entraînement)
    features = (temps_7d + hum_7d + pressure_7d + rain_7d + 
               [day_of_year, month, temp_trend, temp_range, hum_range, 
                pressure_range, gust_max_yesterday, pressure_trend])
    
    return np.array([features]), tomorrow

def predict_tomorrow(model_temp, model_rain, features):
    """Générer les prévisions pour demain"""
    
    # Prédiction température
    temp_pred = model_temp.predict(features)[0]
    
    # Prédiction pluie
    rain_pred = model_rain.predict(features)[0]
    rain_proba = model_rain.predict_proba(features)[0]
    
    # Probabilité de pluie
    rain_prob = rain_proba[1] * 100  # Probabilité de la classe 1 (pluie)
    
    return temp_pred, rain_pred, rain_prob

def calculate_confidence(metrics, recent_weather):
    """
    Calculer un niveau de confiance basé sur:
    - La performance du modèle
    - La stabilité météo récente
    """
    
    # Base: performance du modèle
    temp_confidence = max(0, 100 - (metrics['temp_mae'] * 10))
    rain_confidence = metrics['rain_accuracy'] * 100
    
    # Ajustement selon stabilité récente
    temp_std = np.std(recent_weather)
    stability_factor = max(0, 100 - (temp_std * 5))
    
    # Moyenne pondérée
    overall_confidence = (temp_confidence * 0.4 + rain_confidence * 0.3 + stability_factor * 0.3)
    
    return min(100, max(0, overall_confidence))

def save_predictions(tomorrow, temp_pred, rain_pred, rain_prob, confidence, metrics):
    """Sauvegarder les prévisions au format JSON"""
    
    predictions = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics.get('trained_at', 'unknown'),
        'tomorrow': {
            'date': tomorrow.strftime('%Y-%m-%d'),
            'day_name': tomorrow.strftime('%A'),
            'temperature': {
                'predicted': round(float(temp_pred), 1),
                'min_estimate': round(float(temp_pred) - 2, 1),
                'max_estimate': round(float(temp_pred) + 2, 1)
            },
            'rain': {
                'will_rain': bool(rain_pred),
                'probability': round(float(rain_prob), 0)
            },
            'confidence': round(float(confidence), 0)
        },
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae']:.1f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%"
        }
    }
    
    # Sauvegarder localement
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)
    
    log(f"✅ Prévisions sauvegardées: {OUTPUT_FILE}")
    
    return predictions

def upload_to_server():
    """Uploader le fichier vers WordPress via FTP"""
    
    # Vérifier que FTP est configuré
    if FTP_PASS == "VOTRE_MOT_DE_PASSE_ICI":
        log("⚠️  FTP non configuré - upload ignoré")
        log("   Éditez le script et remplacez 'VOTRE_MOT_DE_PASSE_ICI' par votre mot de passe")
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
        # On est maintenant dans /public_html/.../previsions-meteo/data/
        
        log(f"📤 Upload de predictions.json dans ce dossier...")
        with open(OUTPUT_FILE, 'rb') as f:
            # Crée le fichier predictions.json dans le dossier actuel
            ftp.storbinary('STOR predictions.json', f)
        # Fichier final : /public_html/.../previsions-meteo/data/predictions.json
        
        ftp.quit()
        log("✅ Upload FTP réussi")
        
    except ftplib.error_perm as e:
        log(f"❌ Erreur FTP permissions: {e}")
        log("   Vérifiez le chemin FTP_PATH et les droits d'accès")
    except Exception as e:
        log(f"❌ Erreur FTP: {e}")
        log("   Vérifiez les identifiants FTP (host, user, pass)")

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 60)
    log("🔮 GÉNÉRATION PRÉVISIONS MÉTÉO")
    log("=" * 60)
    
    # 1. Charger les modèles
    model_temp, model_rain, metrics = load_models()
    if not model_temp or not model_rain:
        log("❌ Impossible de charger les modèles")
        return
    
    # 2. Charger les données
    data = load_data()
    if not data or len(data) < 7:
        log("❌ Pas assez de données (minimum 7 jours requis)")
        return
    
    # 3. Préparer les features
    log("🔧 Préparation des features...")
    features, tomorrow = prepare_features_for_tomorrow(data)
    
    # 4. Générer les prévisions
    log("🤖 Génération des prévisions...")
    temp_pred, rain_pred, rain_prob = predict_tomorrow(model_temp, model_rain, features)
    
    # 5. Calculer la confiance
    recent_temps = [data[date]['temp_avg'] for date in sorted(data.keys())[-7:]]
    confidence = calculate_confidence(metrics, recent_temps)
    
    # 6. Sauvegarder
    predictions = save_predictions(tomorrow, temp_pred, rain_pred, rain_prob, confidence, metrics)
    
    # 7. Upload vers serveur
    upload_to_server()
    
    # Afficher le résultat
    log("=" * 60)
    log(f"✅ PRÉVISIONS POUR DEMAIN ({tomorrow.strftime('%d/%m/%Y')})")
    log(f"   🌡️ Température: {temp_pred:.1f}°C (±2°)")
    log(f"   🌧️ Pluie: {rain_prob:.0f}% de probabilité")
    log(f"   📊 Confiance: {confidence:.0f}%")
    log("=" * 60)

if __name__ == "__main__":
    main()
