#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Détection d'Événements Météo Extrêmes
Analyse les prédictions et envoie des alertes pour événements inhabituels
"""

import json
import os
from datetime import datetime
import subprocess

# ============================================
# CONFIGURATION
# ============================================

# Chemins — relatifs à la racine du repo
BASE_DIR         = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PREDICTIONS_FILE = os.path.join(BASE_DIR, "data", "predictions.json")
DATA_FILE        = os.path.join(BASE_DIR, "data", "meteo_data_enriched.json")
EVENTS_LOG       = os.path.join(BASE_DIR, "logs", "events.log")
ALERTS_HISTORY   = os.path.join(BASE_DIR, "data", "alerts_history.json")

os.makedirs(os.path.dirname(EVENTS_LOG), exist_ok=True)
os.makedirs(os.path.dirname(ALERTS_HISTORY), exist_ok=True)

# ============================================
# SEUILS DE DÉTECTION (Vinelz, Suisse)
# ============================================

THRESHOLDS = {
    'heat_wave': {
        'temp_high': 30.0,      # Canicule si > 30°C
        'temp_very_high': 35.0,  # Canicule extrême si > 35°C
        'duration_days': 3       # Sur 3 jours consécutifs
    },
    'cold_wave': {
        'temp_low': 0.0,         # Gel si < 0°C
        'temp_very_low': -10.0,  # Grand froid si < -10°C
        'duration_days': 3
    },
    'heavy_rain': {
        'daily_mm': 20.0,        # Pluie forte si > 20mm/jour
        'extreme_mm': 50.0,      # Pluie extrême si > 50mm/jour
    },
    'strong_wind': {
        'gust_kmh': 60.0,        # Vent fort si > 60 km/h
        'storm_kmh': 90.0,       # Tempête si > 90 km/h
    },
    'temperature_drop': {
        'drop_degrees': 10.0,    # Chute brutale si > 10°C en 24h
    },
    'pressure_drop': {
        'drop_hpa': 15.0,        # Chute brutale si > 15 hPa en 24h
    }
}

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Logger avec timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    with open(EVENTS_LOG, 'a', encoding='utf-8') as f:
        f.write(log_message)

def send_notification(title, message, sound="Glass"):
    """Envoyer une notification macOS"""
    try:
        script = f'display notification "{message}" with title "{title}" sound name "{sound}"'
        subprocess.run(['osascript', '-e', script], check=True)
        log(f"🔔 Notification envoyée: {title}")
    except Exception as e:
        log(f"⚠️  Erreur notification: {e}")

def load_predictions():
    """Charger les prédictions"""
    try:
        with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"❌ Erreur chargement prédictions: {e}")
        return None

def load_historical_data():
    """Charger les données historiques pour contexte"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        # Derniers jours
        dates = sorted(data.keys())[-7:]
        return {date: data[date] for date in dates}
    except Exception as e:
        log(f"⚠️  Erreur chargement données historiques: {e}")
        return {}

def load_alerts_history():
    """Charger l'historique des alertes"""
    try:
        if os.path.exists(ALERTS_HISTORY):
            with open(ALERTS_HISTORY, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except:
        return []

def save_alert(alert):
    """Sauvegarder une alerte dans l'historique"""
    history = load_alerts_history()
    history.append(alert)
    
    # Garder seulement les 100 dernières alertes
    history = history[-100:]
    
    with open(ALERTS_HISTORY, 'w', encoding='utf-8') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)

def check_heat_wave(forecasts):
    """Détecter vague de chaleur"""
    alerts = []
    
    for forecast in forecasts:
        temp = forecast['temperature']['predicted']
        date = forecast['date']
        day_label = forecast['day_label']
        
        # Canicule extrême
        if temp >= THRESHOLDS['heat_wave']['temp_very_high']:
            alert = {
                'type': 'heat_wave_extreme',
                'severity': 'critical',
                'date': date,
                'day_label': day_label,
                'temperature': temp,
                'message': f"🔥 CANICULE EXTRÊME : {temp}°C prévu {day_label}",
                'recommendation': "Restez au frais, hydratez-vous abondamment"
            }
            alerts.append(alert)
            log(f"🔥 ALERTE CANICULE EXTRÊME: {temp}°C le {date}")
            send_notification(
                "🔥 CANICULE EXTRÊME",
                f"{temp}°C prévu {day_label}. Restez au frais !",
                sound="Basso"
            )
        
        # Canicule
        elif temp >= THRESHOLDS['heat_wave']['temp_high']:
            alert = {
                'type': 'heat_wave',
                'severity': 'warning',
                'date': date,
                'day_label': day_label,
                'temperature': temp,
                'message': f"🌡️ Forte chaleur : {temp}°C prévu {day_label}",
                'recommendation': "Évitez l'exposition au soleil aux heures chaudes"
            }
            alerts.append(alert)
            log(f"🌡️ ALERTE CHALEUR: {temp}°C le {date}")
            send_notification(
                "🌡️ Forte Chaleur",
                f"{temp}°C prévu {day_label}",
                sound="Glass"
            )
    
    return alerts

def check_cold_wave(forecasts):
    """Détecter vague de froid / gel"""
    alerts = []
    
    for forecast in forecasts:
        temp = forecast['temperature']['predicted']
        temp_min = forecast['temperature']['min_estimate']
        date = forecast['date']
        day_label = forecast['day_label']
        
        # Grand froid
        if temp <= THRESHOLDS['cold_wave']['temp_very_low']:
            alert = {
                'type': 'extreme_cold',
                'severity': 'critical',
                'date': date,
                'day_label': day_label,
                'temperature': temp,
                'message': f"❄️ GRAND FROID : {temp}°C prévu {day_label}",
                'recommendation': "Protégez-vous du froid, attention aux canalisations"
            }
            alerts.append(alert)
            log(f"❄️ ALERTE GRAND FROID: {temp}°C le {date}")
            send_notification(
                "❄️ GRAND FROID",
                f"{temp}°C prévu {day_label}. Protégez-vous !",
                sound="Basso"
            )
        
        # Gel
        elif temp_min <= THRESHOLDS['cold_wave']['temp_low']:
            alert = {
                'type': 'frost',
                'severity': 'warning',
                'date': date,
                'day_label': day_label,
                'temperature': temp,
                'temperature_min': temp_min,
                'message': f"🧊 Risque de GEL : minimum {temp_min}°C prévu {day_label}",
                'recommendation': "Protégez les plantes, attention au verglas"
            }
            alerts.append(alert)
            log(f"🧊 ALERTE GEL: {temp_min}°C le {date}")
            send_notification(
                "🧊 Risque de Gel",
                f"Minimum {temp_min}°C prévu {day_label}",
                sound="Glass"
            )
    
    return alerts

def check_heavy_rain(forecasts, historical_data):
    """Détecter pluie forte"""
    alerts = []
    
    for forecast in forecasts:
        rain_prob = forecast['rain']['probability']
        date = forecast['date']
        day_label = forecast['day_label']
        
        # Estimer quantité basée sur probabilité et données historiques
        # (Approximation car on n'a pas la quantité prédite exactement)
        if rain_prob > 80:
            # Pluie très probable
            alert = {
                'type': 'heavy_rain',
                'severity': 'warning',
                'date': date,
                'day_label': day_label,
                'rain_probability': rain_prob,
                'message': f"🌧️ Pluie forte probable : {rain_prob}% {day_label}",
                'recommendation': "Prévoyez un parapluie, possibles inondations locales"
            }
            alerts.append(alert)
            log(f"🌧️ ALERTE PLUIE FORTE: {rain_prob}% le {date}")
            send_notification(
                "🌧️ Pluie Forte Prévue",
                f"{rain_prob}% de probabilité {day_label}",
                sound="Glass"
            )
    
    return alerts

def check_temperature_drop(forecasts):
    """Détecter chute brutale de température"""
    alerts = []
    
    if len(forecasts) < 2:
        return alerts
    
    for i in range(1, len(forecasts)):
        temp_today = forecasts[i-1]['temperature']['predicted']
        temp_tomorrow = forecasts[i]['temperature']['predicted']
        drop = temp_today - temp_tomorrow
        
        if drop >= THRESHOLDS['temperature_drop']['drop_degrees']:
            date = forecasts[i]['date']
            day_label = forecasts[i]['day_label']
            
            alert = {
                'type': 'temperature_drop',
                'severity': 'info',
                'date': date,
                'day_label': day_label,
                'temperature_drop': drop,
                'from_temp': temp_today,
                'to_temp': temp_tomorrow,
                'message': f"📉 Chute de température : -{drop:.1f}°C entre aujourd'hui et {day_label}",
                'recommendation': "Adaptez vos vêtements en conséquence"
            }
            alerts.append(alert)
            log(f"📉 ALERTE CHUTE TEMPÉRATURE: -{drop:.1f}°C vers le {date}")
            send_notification(
                "📉 Chute de Température",
                f"-{drop:.1f}°C prévu {day_label}",
                sound="Purr"
            )
    
    return alerts

def detect_events():
    """Fonction principale de détection"""
    
    log("=" * 70)
    log("🔍 DÉTECTION D'ÉVÉNEMENTS MÉTÉO")
    log("=" * 70)
    
    # Charger les données
    predictions_data = load_predictions()
    if not predictions_data:
        log("❌ Impossible de charger les prédictions")
        return
    
    forecasts = predictions_data.get('forecasts', [])
    if not forecasts:
        log("⚠️  Aucune prédiction trouvée")
        return
    
    historical_data = load_historical_data()
    
    log(f"📅 Analyse de {len(forecasts)} prévisions")
    log("")
    
    # Détection de tous les événements
    all_alerts = []
    
    all_alerts.extend(check_heat_wave(forecasts))
    all_alerts.extend(check_cold_wave(forecasts))
    all_alerts.extend(check_heavy_rain(forecasts, historical_data))
    all_alerts.extend(check_temperature_drop(forecasts))
    
    # Résumé
    log("")
    log("=" * 70)
    log("📊 RÉSUMÉ")
    log("=" * 70)
    
    if all_alerts:
        log(f"⚠️  {len(all_alerts)} alerte(s) détectée(s)")
        log("")
        
        # Grouper par sévérité
        critical = [a for a in all_alerts if a['severity'] == 'critical']
        warning = [a for a in all_alerts if a['severity'] == 'warning']
        info = [a for a in all_alerts if a['severity'] == 'info']
        
        if critical:
            log(f"🔴 Alertes CRITIQUES: {len(critical)}")
            for alert in critical:
                log(f"   {alert['message']}")
        
        if warning:
            log(f"🟠 Alertes AVERTISSEMENT: {len(warning)}")
            for alert in warning:
                log(f"   {alert['message']}")
        
        if info:
            log(f"🔵 Alertes INFO: {len(info)}")
            for alert in info:
                log(f"   {alert['message']}")
        
        # Sauvegarder toutes les alertes
        for alert in all_alerts:
            alert['detected_at'] = datetime.now().isoformat()
            save_alert(alert)
        
    else:
        log("✅ Aucun événement extrême détecté")
        log("   Conditions météo normales prévues")
    
    log("")
    log("=" * 70)

# ============================================
# MAIN
# ============================================

def main():
    detect_events()

if __name__ == "__main__":
    main()
