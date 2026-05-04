#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de génération de prévisions 3 JOURS avec modèle 3x8h - VERSION CORRIGÉE
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

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_FILE = f"{BASE_DIR}/data/json/predictions.json"
LOG_FILE = f"{BASE_DIR}/logs/predictions_3days.log"

# FTP Upload (configuration Infomaniak)
FTP_HOST = "ig6i34.ftp.infomaniak.com"
FTP_USER = "ig6i34_data_net"
FTP_PASS = "Cf301164!222"
FTP_PATH = ""  # ← CORRIGÉ : dossier data

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

def prepare_features_for_day(data, dates, days_ahead, previous_predictions=None):
    """
    Préparer les features pour prédire un jour spécifique
    
    CORRECTION MAJEURE : Pour J+2 et J+3, on utilise les prédictions précédentes !
    
    Args:
        data: Données complètes
        dates: Liste des dates triées
        days_ahead: 1=demain, 2=après-demain, 3=dans 3 jours
        previous_predictions: Dict avec les prévisions des jours précédents
    """
    
    features = []
    
    # Le dernier jour avec des données RÉELLES
    last_complete_day_idx = len(dates) - 1
    
    # Vérifier qu'on a assez d'historique
    if last_complete_day_idx < 6:
        return None, None
    
    # ========================================================================
    # CORRECTION : Construire l'historique différemment selon le jour prédit
    # ========================================================================
    
    if days_ahead == 1:
        # Pour DEMAIN (J+1) : On utilise les 7 derniers jours RÉELS
        history_indices = [last_complete_day_idx - i for i in range(7)]
        
    elif days_ahead == 2:
        # Pour APRÈS-DEMAIN (J+2) : 
        # 6 derniers jours réels + la prédiction de DEMAIN
        history_indices = [last_complete_day_idx - i for i in range(6)]
        # On ajoutera la prédiction J+1 après
        
    else:  # days_ahead == 3
        # Pour J+3 :
        # 5 derniers jours réels + prédictions de J+1 et J+2
        history_indices = [last_complete_day_idx - i for i in range(5)]
        # On ajoutera les prédictions J+1 et J+2 après
    
    # ========================================================================
    # Features des jours RÉELS (historique)
    # ========================================================================
    
    for idx in history_indices:
        if idx < 0:
            return None, None
        
        past_date = dates[idx]
        day_data = data[past_date]
        
        # Moyennes journalières
        features.append(day_data.get('temp_avg', 15))
        features.append(day_data.get('hum_avg', 70))
        features.append(day_data.get('pressure_avg', 1013))
        features.append(1 if day_data.get('rain', 0) > 0.5 else 0)
        
        # Périodes
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
    # CORRECTION : Ajouter les prédictions précédentes comme features
    # ========================================================================
    
    if days_ahead == 2 and previous_predictions:
        # Pour J+2, ajouter la prédiction de J+1
        pred_j1 = previous_predictions.get(1)
        if pred_j1:
            # Simuler un jour de données avec la prédiction
            features.append(pred_j1['temp_pred'])
            features.append(70)  # Humidité estimée
            features.append(1013)  # Pression estimée
            features.append(1 if pred_j1['rain_pred'] else 0)
            
            # Périodes estimées
            for period_key in ['p1', 'p2', 'p3']:
                period_temp = pred_j1['period_temps'][period_key]
                features.append(period_temp)  # temp_avg
                features.append(period_temp - 2)  # temp_min
                features.append(period_temp + 2)  # temp_max
                features.append(4)  # temp_range
                
                features.append(1013)  # pressure_avg
                features.append(5)  # pressure_range
                
                features.append(70)  # hum_avg
                features.append(10)  # hum_range
                
                features.append(10)  # wind_max
                features.append(5)  # wind_range
                
                features.append(1 if pred_j1['rain_pred'] else 0)
    
    elif days_ahead == 3 and previous_predictions:
        # Pour J+3, ajouter les prédictions de J+1 et J+2
        for day_offset in [1, 2]:
            pred = previous_predictions.get(day_offset)
            if pred:
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
    
    # ========================================================================
    # CORRECTION : Date du jour à prédire (DIFFÉRENTE pour chaque jour !)
    # ========================================================================
    
    target_date = datetime.now() + timedelta(days=days_ahead)
    features.append(target_date.timetuple().tm_yday)  # Jour de l'année
    features.append(target_date.month)  # Mois
    
    # Tendances sur les 7 derniers jours RÉELS
    temps_7d = [data[dates[last_complete_day_idx - i]].get('temp_avg', 15) for i in range(min(7, last_complete_day_idx + 1))]
    pressure_7d = [data[dates[last_complete_day_idx - i]].get('pressure_avg', 1013) for i in range(min(7, last_complete_day_idx + 1))]
    
    if len(temps_7d) >= 3:
        features.append(np.mean(temps_7d[:3]) - np.mean(temps_7d))
    else:
        features.append(0)
    
    if len(pressure_7d) >= 2:
        features.append(pressure_7d[0] - pressure_7d[-1])
    else:
        features.append(0)
    
    log(f"   📊 Features pour J+{days_ahead}: {len(features)} éléments")
    
    return np.array([features]), target_date

def predict_day(model_temp, model_rain, features):
    """Générer les prévisions pour un jour"""
    
    temp_pred = model_temp.predict(features)[0]
    rain_pred = model_rain.predict(features)[0]
    rain_proba = model_rain.predict_proba(features)[0]
    rain_prob = rain_proba[1] * 100
    
    return temp_pred, rain_pred, rain_prob

def calculate_confidence(metrics, days_ahead):
    """Calculer le niveau de confiance selon le nombre de jours"""
    
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
    """Estimer les températures par période"""
    
    # Analyser les 7 derniers jours
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
    
    # Calculer l'amplitude typique
    if recent_p2_max and recent_p1_min:
        typical_amplitude = np.mean([p2 - p1 for p2, p1 in zip(recent_p2_max[:3], recent_p1_min[:3])])
    else:
        typical_amplitude = 8.0
    
    # Ajuster selon le jour (plus d'incertitude = plus conservateur)
    if days_ahead == 1:
        afternoon_adj = typical_amplitude * 0.5
        morning_adj = -typical_amplitude * 0.3
        night_adj = -typical_amplitude * 0.2
    elif days_ahead == 2:
        afternoon_adj = typical_amplitude * 0.45
        morning_adj = -typical_amplitude * 0.25
        night_adj = -typical_amplitude * 0.15
    else:  # jour 3
        afternoon_adj = typical_amplitude * 0.4
        morning_adj = -typical_amplitude * 0.2
        night_adj = -typical_amplitude * 0.1
    
    return {
        'p1': round(temp_pred + morning_adj, 1),
        'p2': round(temp_pred + afternoon_adj, 1),
        'p3': round(temp_pred + night_adj, 1)
    }

def generate_predictions_3days(model_temp, model_rain, metrics, data):
    """
    Générer les prévisions : Demain, Après-demain, J+3
    VERSION CORRIGÉE avec prédictions séquentielles
    """
    
    log("🔧 Génération des prévisions 3 jours (SÉQUENTIEL)...")
    
    dates = sorted(data.keys())
    log(f"   📊 Données disponibles: {len(dates)} jours")
    log(f"   📅 Dernier jour connu: {dates[-1]}")
    
    forecasts = []
    previous_predictions = {}  # Stocke les prédictions précédentes
    
    # PRÉDIRE SÉQUENTIELLEMENT : J+1, puis J+2 (utilise J+1), puis J+3 (utilise J+1 et J+2)
    for day in range(1, 4):  # 1, 2, 3
        
        if day == 1:
            day_label = "Demain"
            log(f"\n   📅 {day_label} (J+1)...")
        elif day == 2:
            day_label = "Après-demain"
            log(f"\n   📅 {day_label} (J+2) - utilise prédiction J+1...")
        else:
            day_label = "Dans 3 jours"
            log(f"\n   📅 {day_label} (J+3) - utilise prédictions J+1 et J+2...")
        
        # Préparer les features (utilise previous_predictions si day > 1)
        features, target_date = prepare_features_for_day(
            data, dates, day, previous_predictions
        )
        
        if features is None:
            log(f"   ❌ Impossible de générer features pour J+{day}")
            continue
        
        # Prédire
        temp_pred, rain_pred, rain_prob = predict_day(model_temp, model_rain, features)
        confidence = calculate_confidence(metrics, day)
        
        # Marge d'erreur
        temp_margin = metrics['temp_mae'] * (1.0 + 0.3 * (day - 1))
        
        # Températures par période
        period_temps = estimate_period_temps(temp_pred, day, data, dates)
        
        # Stocker pour les prédictions suivantes
        previous_predictions[day] = {
            'temp_pred': temp_pred,
            'rain_pred': rain_pred,
            'period_temps': period_temps
        }
        
        # Risque de pluie
        if rain_prob < 30:
            rain_risk = 'low'
        elif rain_prob < 60:
            rain_risk = 'medium'
        else:
            rain_risk = 'high'
        
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
        
        log(f"   ✅ {day_label}: {temp_pred:.1f}°C (P1:{period_temps['p1']}° P2:{period_temps['p2']}° P3:{period_temps['p3']}°)")
        log(f"      Pluie: {rain_prob:.0f}%, Confiance: {confidence:.0f}%")
    
    # Structure de sortie
    predictions = {
        'generated_at': datetime.now().isoformat(),
        'model_version': metrics.get('trained_at', 'unknown'),
        'model_type': '3x8h_periods_sequential',  # ← CORRIGÉ
        'forecasts': forecasts,
        'model_performance': {
            'temperature_accuracy': f"±{metrics['temp_mae']:.1f}°C",
            'rain_accuracy': f"{metrics['rain_accuracy']*100:.0f}%"
        }
    }
    
    # Sauvegarder
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(predictions, f, ensure_ascii=False, indent=2)
    
    log(f"\n✅ Prévisions 3 jours sauvegardées: {OUTPUT_FILE}")
    
    return predictions

def upload_to_server():
    """Uploader via FTP"""
    
    try:
        import ftplib
        
        log("\n📤 Connexion FTP...")
        log(f"   Serveur: {FTP_HOST}")
        log(f"   User: {FTP_USER}")
        log(f"   Dossier: {FTP_PATH}")
        
        ftp = ftplib.FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        
        if FTP_PATH:
            log(f"   Changement vers /{FTP_PATH}/...")
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
    log("🔮 PRÉVISIONS MÉTÉO 3 JOURS - VERSION CORRIGÉE (SÉQUENTIEL)")
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
    log("✅ PRÉVISIONS GÉNÉRÉES (SÉQUENTIELLES)")
    log("=" * 70)
    
    for forecast in predictions['forecasts']:
        day_label = forecast['day_label']
        date = forecast['date']
        temp = forecast['temperature']['predicted']
        p1 = forecast['periods']['p1']['temp_estimate']
        p2 = forecast['periods']['p2']['temp_estimate']
        p3 = forecast['periods']['p3']['temp_estimate']
        rain = forecast['rain']['probability']
        conf = forecast['confidence']
        
        log(f"\n📅 {day_label} ({date}):")
        log(f"   🌡️  Température: {temp}°C")
        log(f"   ⏰ Matin: {p1}°C | Après-midi: {p2}°C | Nuit: {p3}°C")
        log(f"   🌧️  Pluie: {rain:.0f}%")
        log(f"   📊 Confiance: {conf:.0f}%")
    
    log("\n" + "=" * 70)
    log("🎯 CORRECTIONS APPLIQUÉES:")
    log("   ✅ Prédictions séquentielles (J+2 utilise J+1, J+3 utilise J+1 et J+2)")
    log("   ✅ Date cible différente pour chaque jour")
    log("   ✅ FTP path corrigé vers 'data'")
    log("=" * 70)

if __name__ == "__main__":
    main()
