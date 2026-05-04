#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validation Continue - Comparaison Quotidienne Prédictions vs Réalité
Exécuté chaque jour pour mesurer la précision réelle du modèle
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
PREDICTIONS_FILE = f"{BASE_DIR}/data/json/predictions.json"
VALIDATION_FILE = f"{BASE_DIR}/data/validation/validation_history.json"
LOG_FILE = f"{BASE_DIR}/logs/validation.log"

os.makedirs(os.path.dirname(VALIDATION_FILE), exist_ok=True)
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Logger avec timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message)

def load_predictions():
    """Charger les prédictions du fichier"""
    try:
        with open(PREDICTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"❌ Erreur chargement prédictions: {e}")
        return None

def load_actual_data():
    """Charger les données météo réelles"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"❌ Erreur chargement données: {e}")
        return None

def load_validation_history():
    """Charger l'historique des validations"""
    try:
        if os.path.exists(VALIDATION_FILE):
            with open(VALIDATION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        log(f"⚠️  Erreur chargement historique: {e}")
        return []

def save_validation_history(history):
    """Sauvegarder l'historique des validations"""
    try:
        with open(VALIDATION_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
        log(f"✅ Historique sauvegardé: {len(history)} entrées")
    except Exception as e:
        log(f"❌ Erreur sauvegarde historique: {e}")

def validate_predictions():
    """Valider les prédictions contre la réalité"""
    
    log("=" * 70)
    log("📊 VALIDATION CONTINUE - COMPARAISON PRÉDICTIONS vs RÉALITÉ")
    log("=" * 70)
    
    # Charger les données
    predictions_data = load_predictions()
    actual_data = load_actual_data()
    
    if not predictions_data or not actual_data:
        log("❌ Impossible de charger les données")
        return
    
    # Date de génération des prédictions
    pred_date = predictions_data.get('generated_at', '')[:10]
    log(f"📅 Prédictions du: {pred_date}")
    
    forecasts = predictions_data.get('forecasts', [])
    if not forecasts:
        log("❌ Aucune prédiction trouvée")
        return
    
    # Analyser chaque horizon
    results = []
    
    for forecast in forecasts:
        horizon = forecast['day_number']
        pred_date_str = forecast['date']
        
        # Vérifier si les données réelles sont disponibles
        if pred_date_str not in actual_data:
            log(f"⏳ Données réelles pas encore disponibles pour {pred_date_str} (horizon {horizon})")
            continue
        
        actual = actual_data[pred_date_str]
        
        # Température
        temp_pred = forecast['temperature']['predicted']
        temp_actual = actual.get('temp_avg')
        
        if temp_actual is None:
            log(f"⚠️  Température réelle manquante pour {pred_date_str}")
            continue
        
        temp_error = abs(temp_pred - temp_actual)
        
        # Pluie
        rain_pred = forecast['rain']['will_rain']
        rain_actual = actual.get('rain', 0) > 0.5
        rain_correct = rain_pred == rain_actual
        
        # Résultats
        result = {
            'validation_date': datetime.now().isoformat(),
            'prediction_date': pred_date,
            'target_date': pred_date_str,
            'horizon': horizon,
            'horizon_label': forecast['day_label'],
            'temperature': {
                'predicted': temp_pred,
                'actual': temp_actual,
                'error': round(temp_error, 2),
                'min_estimate': forecast['temperature']['min_estimate'],
                'max_estimate': forecast['temperature']['max_estimate'],
                'within_bounds': forecast['temperature']['min_estimate'] <= temp_actual <= forecast['temperature']['max_estimate']
            },
            'rain': {
                'predicted': rain_pred,
                'actual': rain_actual,
                'correct': rain_correct,
                'probability': forecast['rain']['probability']
            },
            'confidence': forecast['confidence'],
            'model_type': predictions_data.get('model_type', 'unknown')
        }
        
        results.append(result)
        
        # Logger
        log("")
        log(f"📍 {forecast['day_label']} ({pred_date_str}) - Horizon {horizon}")
        log(f"   🌡️  Température:")
        log(f"      Prédite: {temp_pred}°C")
        log(f"      Réelle:  {temp_actual}°C")
        log(f"      Erreur:  {temp_error:.2f}°C {'✅' if temp_error < 1.0 else '⚠️' if temp_error < 2.0 else '❌'}")
        log(f"      Bornes:  [{forecast['temperature']['min_estimate']}°C - {forecast['temperature']['max_estimate']}°C]")
        log(f"      Dans bornes: {'✅' if result['temperature']['within_bounds'] else '❌'}")
        log(f"   🌧️  Pluie:")
        log(f"      Prédite: {'OUI' if rain_pred else 'NON'} ({forecast['rain']['probability']}%)")
        log(f"      Réelle:  {'OUI' if rain_actual else 'NON'}")
        log(f"      {'✅ CORRECT' if rain_correct else '❌ INCORRECT'}")
    
    if not results:
        log("⏳ Aucune validation possible (données réelles pas encore disponibles)")
        return
    
    # Statistiques globales
    log("")
    log("=" * 70)
    log("📊 STATISTIQUES GLOBALES")
    log("=" * 70)
    
    temp_errors = [r['temperature']['error'] for r in results]
    rain_accuracy = sum(1 for r in results if r['rain']['correct']) / len(results) * 100
    within_bounds = sum(1 for r in results if r['temperature']['within_bounds']) / len(results) * 100
    
    log(f"   Validations effectuées: {len(results)}")
    log(f"   MAE Température: {np.mean(temp_errors):.2f}°C")
    log(f"   MAE par horizon:")
    
    for h in [0, 1, 2]:
        horizon_errors = [r['temperature']['error'] for r in results if r['horizon'] == h]
        if horizon_errors:
            log(f"      H={h}: {np.mean(horizon_errors):.2f}°C ({len(horizon_errors)} validations)")
    
    log(f"   Précision Pluie: {rain_accuracy:.1f}%")
    log(f"   Prédictions dans bornes: {within_bounds:.1f}%")
    
    # Sauvegarder dans l'historique
    history = load_validation_history()
    history.extend(results)
    save_validation_history(history)
    
    log("")
    log("=" * 70)
    log("✅ VALIDATION TERMINÉE")
    log("=" * 70)

# ============================================
# MAIN
# ============================================

def main():
    validate_predictions()

if __name__ == "__main__":
    main()
