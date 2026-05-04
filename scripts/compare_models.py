#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de COMPARAISON entre modèle original et modèle saisonnier
Analyse l'amélioration apportée par les features saisonnières
"""

import json
import os
from datetime import datetime
import numpy as np
from sklearn.metrics import mean_absolute_error, mean_squared_error
import joblib

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_FILE = f"{BASE_DIR}/data/analysis/model_comparison.json"

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

# ============================================
# FONCTIONS
# ============================================

def load_data():
    """Charger les données enrichies"""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data

def get_season_name(month):
    """Retourne le nom de la saison"""
    if month in [12, 1, 2]:
        return "Hiver"
    elif month in [3, 4, 5]:
        return "Printemps"
    elif month in [6, 7, 8]:
        return "Été"
    else:
        return "Automne"

def get_season_number(month):
    """Retourne le numéro de la saison"""
    if month in [12, 1, 2]:
        return 0
    elif month in [3, 4, 5]:
        return 1
    elif month in [6, 7, 8]:
        return 2
    else:
        return 3

def analyze_models():
    """Compare les deux modèles sur les métriques d'entraînement"""
    
    print("=" * 80)
    print("📊 COMPARAISON MODÈLE ORIGINAL vs SAISONNIER")
    print("=" * 80)
    print()
    
    # Charger les métriques
    try:
        with open(f"{MODEL_DIR}/metrics_multihorizon.json", 'r') as f:
            metrics_old = json.load(f)
        print("✅ Métriques modèle original chargées")
    except:
        print("❌ Impossible de charger metrics_multihorizon.json")
        metrics_old = None
    
    try:
        with open(f"{MODEL_DIR}/metrics_seasonal.json", 'r') as f:
            metrics_new = json.load(f)
        print("✅ Métriques modèle saisonnier chargées")
    except:
        print("❌ Impossible de charger metrics_seasonal.json")
        metrics_new = None
    
    if not metrics_old or not metrics_new:
        print("\n⚠️  Les deux modèles doivent être entraînés pour la comparaison")
        return
    
    print()
    print("=" * 80)
    print("📈 MÉTRIQUES D'ENTRAÎNEMENT")
    print("=" * 80)
    
    # Tableau de comparaison
    print()
    print(f"{'Métrique':<30} {'Original':<15} {'Saisonnier':<15} {'Amélioration':<15}")
    print("-" * 80)
    
    # MAE Température
    mae_old = metrics_old['temp_mae']
    mae_new = metrics_new['temp_mae']
    improvement = ((mae_old - mae_new) / mae_old) * 100
    
    print(f"{'MAE Température (°C)':<30} {mae_old:<15.3f} {mae_new:<15.3f} {improvement:>+14.1f}%")
    
    # Précision Pluie
    acc_old = metrics_old['rain_accuracy'] * 100
    acc_new = metrics_new['rain_accuracy'] * 100
    acc_diff = acc_new - acc_old
    
    print(f"{'Précision Pluie (%)':<30} {acc_old:<15.1f} {acc_new:<15.1f} {acc_diff:>+14.1f}%")
    
    # Features
    n_feat_old = metrics_old['n_features']
    n_feat_new = metrics_new['n_features']
    feat_diff = n_feat_new - n_feat_old
    
    print(f"{'Nombre de features':<30} {n_feat_old:<15} {n_feat_new:<15} {feat_diff:>+14}")
    
    # Échantillons
    n_samples_old = metrics_old['n_samples']
    n_samples_new = metrics_new['n_samples']
    
    print(f"{'Échantillons entraînement':<30} {n_samples_old:<15} {n_samples_new:<15} {'=':<15}")
    
    print("-" * 80)
    
    # RMSE estimé
    rmse_estimate_old = mae_old * 1.25  # RMSE ≈ 1.25 × MAE typiquement
    rmse_estimate_new = mae_new * 1.25
    
    print(f"{'RMSE estimé (°C)':<30} {rmse_estimate_old:<15.3f} {rmse_estimate_new:<15.3f}")
    
    print()
    print("=" * 80)
    print("🎯 RÉSUMÉ DES AMÉLIORATIONS")
    print("=" * 80)
    print()
    
    if improvement > 0:
        print(f"✅ Réduction du MAE: {improvement:.1f}%")
        print(f"   Précision gagnée: {(mae_old - mae_new):.3f}°C")
        print()
        
        if improvement > 20:
            print("🌟 AMÉLIORATION EXCELLENTE (>20%)")
        elif improvement > 10:
            print("✨ AMÉLIORATION TRÈS BONNE (10-20%)")
        elif improvement > 5:
            print("👍 AMÉLIORATION BONNE (5-10%)")
        else:
            print("📊 AMÉLIORATION MODÉRÉE (<5%)")
    else:
        print(f"⚠️  Légère dégradation: {abs(improvement):.1f}%")
        print("   Cela peut arriver avec un petit ensemble de données")
        print("   → Continuez à collecter des données pendant 1-2 mois")
    
    print()
    
    # Analyse des features saisonnières
    if metrics_new.get('seasonal_features'):
        print("=" * 80)
        print("🌍 NORMALES SAISONNIÈRES CALCULÉES")
        print("=" * 80)
        print()
        
        if 'seasonal_normals' in metrics_new:
            normals = metrics_new['seasonal_normals']
            seasons = ['Hiver', 'Printemps', 'Été', 'Automne']
            
            print(f"{'Saison':<15} {'Temp. Normale':<20} {'Écart-type':<20}")
            print("-" * 55)
            
            for i, season_name in enumerate(seasons):
                if str(i) in normals:
                    temp = normals[str(i)]['temp']
                    std = normals[str(i)]['temp_std']
                    print(f"{season_name:<15} {temp:>8.1f}°C {'':<10} ±{std:.1f}°C")
            
            print()
    
    # Recommandations
    print("=" * 80)
    print("💡 RECOMMANDATIONS")
    print("=" * 80)
    print()
    
    if improvement > 5:
        print("✅ Le modèle saisonnier performe mieux !")
        print("   → Utilisez predict_weather_seasonal.py pour vos prévisions")
        print()
        print("📝 Prochaines étapes suggérées :")
        print("   1. Validation continue (30 jours) pour confirmer l'amélioration")
        print("   2. Ajout des intervalles de confiance")
        print("   3. Détection d'événements extrêmes")
        print("   4. Modèle ensembliste (XGBoost + RF)")
    else:
        print("📊 Résultats similaires entre les deux modèles")
        print("   → Collectez plus de données (objectif: 12 mois)")
        print("   → Les features saisonnières sont plus utiles avec 1+ an de données")
        print()
        print("💡 En attendant :")
        print("   - Continuez avec predict_weather_multihorizon.py")
        print("   - Réentraînez dans 1-2 mois avec plus de données")
    
    print()
    
    # Sauvegarder l'analyse
    comparison = {
        'generated_at': datetime.now().isoformat(),
        'original_model': {
            'mae': mae_old,
            'rain_accuracy': metrics_old['rain_accuracy'],
            'n_features': n_feat_old,
            'n_samples': n_samples_old,
            'trained_at': metrics_old.get('trained_at', 'unknown')
        },
        'seasonal_model': {
            'mae': mae_new,
            'rain_accuracy': metrics_new['rain_accuracy'],
            'n_features': n_feat_new,
            'n_samples': n_samples_new,
            'trained_at': metrics_new.get('trained_at', 'unknown'),
            'seasonal_features': True
        },
        'improvements': {
            'mae_reduction_percent': improvement,
            'mae_reduction_absolute': mae_old - mae_new,
            'rain_accuracy_change': acc_diff,
            'features_added': feat_diff
        },
        'recommendation': 'use_seasonal' if improvement > 5 else 'collect_more_data'
    }
    
    with open(OUTPUT_FILE, 'w') as f:
        json.dump(comparison, f, indent=2)
    
    print(f"💾 Analyse sauvegardée: {OUTPUT_FILE}")
    print()

def analyze_by_season():
    """
    Analyse détaillée par saison (nécessite données de test)
    À implémenter après avoir collecté plus de données
    """
    print("=" * 80)
    print("📊 ANALYSE PAR SAISON")
    print("=" * 80)
    print()
    print("⚠️  Cette analyse nécessite un ensemble de test séparé")
    print("   → À implémenter après avoir collecté 12+ mois de données")
    print()
    print("📝 Analyses futures prévues :")
    print("   - MAE par saison (Hiver, Printemps, Été, Automne)")
    print("   - Performance sur vagues de chaleur/froid")
    print("   - Erreurs sur transitions saisonnières")
    print()

# ============================================
# MAIN
# ============================================

def main():
    analyze_models()
    analyze_by_season()

if __name__ == "__main__":
    main()
