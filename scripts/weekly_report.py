#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rapport Hebdomadaire de Performance
Analyse des 7 derniers jours de validation
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
VALIDATION_FILE = f"{BASE_DIR}/data/validation/validation_history.json"
REPORTS_DIR = f"{BASE_DIR}/data/reports"
LOG_FILE = f"{BASE_DIR}/logs/weekly_report.log"

os.makedirs(REPORTS_DIR, exist_ok=True)
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

def load_validation_history():
    """Charger l'historique des validations"""
    try:
        if os.path.exists(VALIDATION_FILE):
            with open(VALIDATION_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        log(f"❌ Erreur chargement historique: {e}")
        return []

def get_recent_validations(history, days=7):
    """Récupérer les validations des N derniers jours"""
    cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
    return [v for v in history if v['validation_date'] >= cutoff_date]

def generate_weekly_report():
    """Générer le rapport hebdomadaire"""
    
    log("=" * 70)
    log("📊 RAPPORT HEBDOMADAIRE DE PERFORMANCE")
    log("=" * 70)
    log(f"📅 Période: {(datetime.now() - timedelta(days=7)).strftime('%d/%m/%Y')} → {datetime.now().strftime('%d/%m/%Y')}")
    log("")
    
    # Charger l'historique
    history = load_validation_history()
    
    if not history:
        log("❌ Aucune donnée de validation disponible")
        return
    
    # Récupérer les 7 derniers jours
    recent = get_recent_validations(history, days=7)
    
    if not recent:
        log("⚠️  Aucune validation dans les 7 derniers jours")
        return
    
    log(f"✅ {len(recent)} validations trouvées")
    log("")
    
    # ============================================
    # ANALYSE PAR HORIZON
    # ============================================
    
    log("=" * 70)
    log("📊 PERFORMANCE PAR HORIZON")
    log("=" * 70)
    log("")
    
    horizons_data = {}
    
    for h in [0, 1, 2]:
        horizon_vals = [v for v in recent if v['horizon'] == h]
        
        if not horizon_vals:
            continue
        
        temp_errors = [v['temperature']['error'] for v in horizon_vals]
        rain_correct = sum(1 for v in horizon_vals if v['rain']['correct'])
        within_bounds = sum(1 for v in horizon_vals if v['temperature']['within_bounds'])
        
        mae = np.mean(temp_errors)
        mae_std = np.std(temp_errors)
        max_error = max(temp_errors)
        min_error = min(temp_errors)
        rain_acc = (rain_correct / len(horizon_vals)) * 100
        bounds_acc = (within_bounds / len(horizon_vals)) * 100
        
        horizons_data[h] = {
            'count': len(horizon_vals),
            'mae': mae,
            'mae_std': mae_std,
            'max_error': max_error,
            'min_error': min_error,
            'rain_accuracy': rain_acc,
            'bounds_accuracy': bounds_acc
        }
        
        label = ['Aujourd\'hui (J+0)', 'Demain (J+1)', 'Après-demain (J+2)'][h]
        
        log(f"📍 {label}")
        log(f"   Validations:        {len(horizon_vals)}")
        log(f"   MAE Température:    {mae:.2f}°C ± {mae_std:.2f}°C")
        log(f"   Erreur min/max:     {min_error:.2f}°C / {max_error:.2f}°C")
        log(f"   Précision Pluie:    {rain_acc:.1f}%")
        log(f"   Dans bornes:        {bounds_acc:.1f}%")
        log("")
    
    # ============================================
    # TENDANCES
    # ============================================
    
    log("=" * 70)
    log("📈 TENDANCES")
    log("=" * 70)
    log("")
    
    # Comparer avec la semaine précédente
    previous_week = get_recent_validations(history, days=14)
    previous_week = [v for v in previous_week if v['validation_date'] < (datetime.now() - timedelta(days=7)).isoformat()]
    
    if previous_week:
        current_mae = np.mean([v['temperature']['error'] for v in recent])
        previous_mae = np.mean([v['temperature']['error'] for v in previous_week])
        improvement = ((previous_mae - current_mae) / previous_mae) * 100
        
        log(f"   MAE cette semaine:      {current_mae:.2f}°C")
        log(f"   MAE semaine précédente: {previous_mae:.2f}°C")
        
        if improvement > 0:
            log(f"   📈 Amélioration:        +{improvement:.1f}% ✅")
        else:
            log(f"   📉 Dégradation:         {improvement:.1f}% ⚠️")
    else:
        log("   ℹ️  Pas de données pour comparaison avec semaine précédente")
    
    log("")
    
    # ============================================
    # ALERTES
    # ============================================
    
    log("=" * 70)
    log("⚠️  ALERTES & RECOMMANDATIONS")
    log("=" * 70)
    log("")
    
    alerts = []
    
    # Alert: MAE > 1.0°C
    overall_mae = np.mean([v['temperature']['error'] for v in recent])
    if overall_mae > 1.0:
        alerts.append({
            'level': 'warning',
            'message': f"MAE élevé ({overall_mae:.2f}°C > 1.0°C)",
            'recommendation': "Considérer un réentraînement du modèle"
        })
    
    # Alert: Précision pluie < 80%
    rain_correct = sum(1 for v in recent if v['rain']['correct'])
    rain_acc = (rain_correct / len(recent)) * 100
    if rain_acc < 80:
        alerts.append({
            'level': 'warning',
            'message': f"Précision pluie faible ({rain_acc:.1f}% < 80%)",
            'recommendation': "Vérifier les seuils de détection de pluie"
        })
    
    # Alert: Dégradation par rapport à semaine précédente
    if previous_week and improvement < -10:
        alerts.append({
            'level': 'critical',
            'message': f"Dégradation importante ({improvement:.1f}%)",
            'recommendation': "Réentraîner le modèle immédiatement"
        })
    
    # Alert: Peu de validations
    if len(recent) < 14:  # Moins de 2 validations/jour en moyenne
        alerts.append({
            'level': 'info',
            'message': f"Peu de validations ({len(recent)} en 7 jours)",
            'recommendation': "Vérifier que les prédictions quotidiennes fonctionnent"
        })
    
    if alerts:
        for alert in alerts:
            emoji = '⚠️' if alert['level'] == 'warning' else '🔴' if alert['level'] == 'critical' else 'ℹ️'
            log(f"   {emoji} {alert['message']}")
            log(f"      → {alert['recommendation']}")
            log("")
    else:
        log("   ✅ Aucune alerte - Performance nominale")
        log("")
    
    # ============================================
    # SAUVEGARDE DU RAPPORT
    # ============================================
    
    report_date = datetime.now().strftime('%Y-%m-%d')
    report_file = f"{REPORTS_DIR}/weekly_report_{report_date}.json"
    
    report = {
        'generated_at': datetime.now().isoformat(),
        'period_start': (datetime.now() - timedelta(days=7)).isoformat(),
        'period_end': datetime.now().isoformat(),
        'validations_count': len(recent),
        'overall_mae': round(overall_mae, 3),
        'rain_accuracy': round(rain_acc, 1),
        'horizons': {str(k): v for k, v in horizons_data.items()},
        'alerts': alerts,
        'comparison_previous_week': {
            'current_mae': round(current_mae, 3) if previous_week else None,
            'previous_mae': round(previous_mae, 3) if previous_week else None,
            'improvement_percent': round(improvement, 1) if previous_week else None
        }
    }
    
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    log("=" * 70)
    log("✅ RAPPORT SAUVEGARDÉ")
    log("=" * 70)
    log(f"📁 {report_file}")
    log("")

# ============================================
# MAIN
# ============================================

def main():
    generate_weekly_report()

if __name__ == "__main__":
    main()
