#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Visualisation des features saisonnières et de leur impact
Génère des graphiques pour comprendre l'amélioration
"""

import json
import os
from datetime import datetime, timedelta
import numpy as np
import matplotlib.pyplot as plt
import joblib

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
MODEL_DIR = f"{BASE_DIR}/data/models"
OUTPUT_DIR = f"{BASE_DIR}/data/visualizations"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================
# FONCTIONS DE VISUALISATION
# ============================================

def plot_seasonal_normals():
    """Graphique des normales saisonnières"""
    
    try:
        seasonal_normals = joblib.load(f"{MODEL_DIR}/seasonal_normals.pkl")
    except:
        print("❌ seasonal_normals.pkl introuvable - entraînez d'abord le modèle saisonnier")
        return
    
    seasons = ['Hiver', 'Printemps', 'Été', 'Automne']
    temps = [seasonal_normals[i]['temp'] for i in range(4)]
    stds = [seasonal_normals[i]['temp_std'] for i in range(4)]
    
    fig, ax = plt.subplots(figsize=(10, 6))
    
    x = np.arange(len(seasons))
    bars = ax.bar(x, temps, yerr=stds, capsize=5, alpha=0.7, color=['#4A90E2', '#7ED321', '#F5A623', '#D0021B'])
    
    ax.set_xlabel('Saison', fontsize=12)
    ax.set_ylabel('Température (°C)', fontsize=12)
    ax.set_title('Normales Saisonnières ± Écart-type', fontsize=14, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(seasons)
    ax.grid(axis='y', alpha=0.3)
    
    # Annotations
    for i, (temp, std) in enumerate(zip(temps, stds)):
        ax.text(i, temp + std + 1, f'{temp:.1f}°C\n±{std:.1f}°C', 
                ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/seasonal_normals.png", dpi=300)
    print(f"✅ Graphique sauvegardé: {OUTPUT_DIR}/seasonal_normals.png")
    plt.close()

def plot_day_length_variation():
    """Graphique de la variation de la durée du jour sur l'année"""
    
    # Calcul simplifié pour Vinelz
    days = np.arange(1, 366)

    # Approximation de la durée du jour
    declination = 23.45 * np.sin(np.radians((360/365) * (days - 81)))
    lat_rad = np.radians(47.09)  # Vinelz, Canton de Berne
    
    day_lengths = []
    for decl in declination:
        decl_rad = np.radians(decl)
        cos_ha = -np.tan(lat_rad) * np.tan(decl_rad)
        cos_ha = np.clip(cos_ha, -1, 1)
        hour_angle = np.degrees(np.arccos(cos_ha))
        day_length = 2 * hour_angle / 15
        day_lengths.append(day_length)
    
    fig, ax = plt.subplots(figsize=(12, 6))
    
    ax.plot(days, day_lengths, linewidth=2, color='#F5A623')
    ax.fill_between(days, day_lengths, alpha=0.3, color='#F5A623')
    
    # Marqueurs saisonniers
    ax.axvline(80, color='#7ED321', linestyle='--', alpha=0.5, label='Équinoxe printemps')
    ax.axvline(172, color='#D0021B', linestyle='--', alpha=0.5, label='Solstice été')
    ax.axvline(266, color='#F5A623', linestyle='--', alpha=0.5, label='Équinoxe automne')
    ax.axvline(355, color='#4A90E2', linestyle='--', alpha=0.5, label='Solstice hiver')
    
    ax.set_xlabel('Jour de l\'année', fontsize=12)
    ax.set_ylabel('Durée du jour (heures)', fontsize=12)
    ax.set_title('Variation Annuelle de la Durée du Jour (Vinelz, Canton de Berne, 47.09°N)',
                 fontsize=14, fontweight='bold')
    ax.grid(alpha=0.3)
    ax.legend(loc='upper right')
    
    # Annotations min/max
    min_idx = np.argmin(day_lengths)
    max_idx = np.argmax(day_lengths)
    ax.annotate(f'Min: {day_lengths[min_idx]:.1f}h', 
                xy=(min_idx, day_lengths[min_idx]), 
                xytext=(min_idx + 30, day_lengths[min_idx] - 1),
                arrowprops=dict(arrowstyle='->', color='blue'))
    ax.annotate(f'Max: {day_lengths[max_idx]:.1f}h', 
                xy=(max_idx, day_lengths[max_idx]), 
                xytext=(max_idx - 30, day_lengths[max_idx] + 1),
                arrowprops=dict(arrowstyle='->', color='red'))
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/day_length_variation.png", dpi=300)
    print(f"✅ Graphique sauvegardé: {OUTPUT_DIR}/day_length_variation.png")
    plt.close()

def plot_feature_importance():
    """Graphique de l'importance des features"""
    
    try:
        model = joblib.load(f"{MODEL_DIR}/model_temp_seasonal.pkl")
    except:
        print("❌ model_temp_seasonal.pkl introuvable")
        return
    
    # Noms des features (simplifié - liste complète trop longue)
    # On se concentre sur les features saisonnières
    seasonal_feature_names = [
        'day_of_year_sin', 'day_of_year_cos',
        'season', 'season_progress',
        'day_length', 'solar_elevation', 'day_length_change',
        'temp_anomaly', 'temp_anomaly_std', 'pressure_anomaly',
        'seasonal_temp_mean', 'seasonal_temp_std', 'seasonal_temp_trend', 'seasonal_pressure_mean',
        'is_season_transition',
        'month_sin', 'month_cos'
    ]
    
    # Indices approximatifs des features saisonnières (à la fin)
    n_features = len(model.feature_importances_)
    seasonal_start_idx = n_features - 17
    
    seasonal_importances = model.feature_importances_[seasonal_start_idx:]
    
    # Trier par importance
    sorted_idx = np.argsort(seasonal_importances)[::-1]
    sorted_names = [seasonal_feature_names[i] for i in sorted_idx]
    sorted_importances = seasonal_importances[sorted_idx]
    
    fig, ax = plt.subplots(figsize=(12, 8))
    
    y_pos = np.arange(len(sorted_names))
    bars = ax.barh(y_pos, sorted_importances, color='#4A90E2', alpha=0.7)
    
    # Colorier les 3 plus importantes
    for i in range(min(3, len(bars))):
        bars[i].set_color('#D0021B')
        bars[i].set_alpha(0.9)
    
    ax.set_yticks(y_pos)
    ax.set_yticklabels(sorted_names, fontsize=10)
    ax.set_xlabel('Importance', fontsize=12)
    ax.set_title('Importance des Features Saisonnières', fontsize=14, fontweight='bold')
    ax.grid(axis='x', alpha=0.3)
    
    # Annotations
    for i, (name, imp) in enumerate(zip(sorted_names, sorted_importances)):
        ax.text(imp + 0.001, i, f'{imp:.4f}', va='center', fontsize=9)
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/seasonal_feature_importance.png", dpi=300)
    print(f"✅ Graphique sauvegardé: {OUTPUT_DIR}/seasonal_feature_importance.png")
    plt.close()

def plot_cyclical_encoding():
    """Illustre l'encodage cyclique sin/cos"""
    
    days = np.arange(1, 366)
    
    # Encodage brut
    day_raw = days / 365.25
    
    # Encodage cyclique
    day_sin = np.sin(2 * np.pi * days / 365.25)
    day_cos = np.cos(2 * np.pi * days / 365.25)
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. Encodage brut
    axes[0, 0].plot(days, day_raw, linewidth=2, color='#4A90E2')
    axes[0, 0].set_title('Encodage Brut (Problématique)', fontweight='bold')
    axes[0, 0].set_xlabel('Jour de l\'année')
    axes[0, 0].set_ylabel('Valeur normalisée')
    axes[0, 0].grid(alpha=0.3)
    axes[0, 0].axvline(1, color='red', linestyle='--', alpha=0.5, label='1er janvier')
    axes[0, 0].axvline(365, color='red', linestyle='--', alpha=0.5, label='31 décembre')
    axes[0, 0].legend()
    axes[0, 0].text(180, 0.8, 'Distance 1→365 = 364 ❌', fontsize=10, ha='center',
                    bbox=dict(boxstyle='round', facecolor='yellow', alpha=0.3))
    
    # 2. Composante sin
    axes[0, 1].plot(days, day_sin, linewidth=2, color='#7ED321')
    axes[0, 1].set_title('Composante Sinusoidale', fontweight='bold')
    axes[0, 1].set_xlabel('Jour de l\'année')
    axes[0, 1].set_ylabel('sin(2π × jour/365.25)')
    axes[0, 1].grid(alpha=0.3)
    axes[0, 1].axhline(0, color='black', linewidth=0.5)
    
    # 3. Composante cos
    axes[1, 0].plot(days, day_cos, linewidth=2, color='#F5A623')
    axes[1, 0].set_title('Composante Cosinusoidale', fontweight='bold')
    axes[1, 0].set_xlabel('Jour de l\'année')
    axes[1, 0].set_ylabel('cos(2π × jour/365.25)')
    axes[1, 0].grid(alpha=0.3)
    axes[1, 0].axhline(0, color='black', linewidth=0.5)
    
    # 4. Représentation 2D (cercle)
    axes[1, 1].plot(day_cos, day_sin, linewidth=2, color='#D0021B')
    axes[1, 1].scatter([day_cos[0]], [day_sin[0]], s=100, c='green', 
                       marker='o', label='1er janvier', zorder=5)
    axes[1, 1].scatter([day_cos[-1]], [day_sin[-1]], s=100, c='blue', 
                       marker='s', label='31 décembre', zorder=5)
    axes[1, 1].set_title('Encodage Cyclique 2D (Cercle)', fontweight='bold')
    axes[1, 1].set_xlabel('cos(2π × jour/365.25)')
    axes[1, 1].set_ylabel('sin(2π × jour/365.25)')
    axes[1, 1].grid(alpha=0.3)
    axes[1, 1].legend()
    axes[1, 1].set_aspect('equal')
    axes[1, 1].text(0, 0, 'Distance 1→365 ≈ 0 ✅', fontsize=10, ha='center',
                    bbox=dict(boxstyle='round', facecolor='lightgreen', alpha=0.5))
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/cyclical_encoding_explained.png", dpi=300)
    print(f"✅ Graphique sauvegardé: {OUTPUT_DIR}/cyclical_encoding_explained.png")
    plt.close()

def plot_comparison_summary():
    """Graphique de comparaison global"""
    
    try:
        with open(f"{BASE_DIR}/data/analysis/model_comparison.json", 'r') as f:
            comparison = json.load(f)
    except:
        print("⚠️  Exécutez d'abord compare_models.py")
        return
    
    mae_old = comparison['original_model']['mae']
    mae_new = comparison['seasonal_model']['mae']
    improvement = comparison['improvements']['mae_reduction_percent']
    
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
    
    # 1. Comparaison MAE
    models = ['Original', 'Saisonnier']
    maes = [mae_old, mae_new]
    colors = ['#4A90E2', '#7ED321']
    
    bars = ax1.bar(models, maes, color=colors, alpha=0.7, edgecolor='black', linewidth=2)
    ax1.set_ylabel('MAE (°C)', fontsize=12)
    ax1.set_title('Comparaison de la Précision', fontsize=14, fontweight='bold')
    ax1.grid(axis='y', alpha=0.3)
    
    # Annotations
    for i, (model, mae, bar) in enumerate(zip(models, maes, bars)):
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2, height + 0.01,
                f'{mae:.3f}°C', ha='center', va='bottom', fontsize=12, fontweight='bold')
    
    # Flèche d'amélioration
    if improvement > 0:
        ax1.annotate('', xy=(1, mae_new), xytext=(1, mae_old),
                    arrowprops=dict(arrowstyle='->', lw=2, color='green'))
        ax1.text(1.15, (mae_old + mae_new)/2, f'{improvement:.1f}%\namélioration',
                ha='left', va='center', fontsize=11, color='green', fontweight='bold')
    
    # 2. Nombre de features
    n_feat_old = comparison['original_model']['n_features']
    n_feat_new = comparison['seasonal_model']['n_features']
    
    # Pie chart
    labels = ['Features\noriginales', 'Features\nsaisonnières']
    sizes = [n_feat_old, n_feat_new - n_feat_old]
    colors_pie = ['#4A90E2', '#F5A623']
    explode = (0, 0.1)
    
    ax2.pie(sizes, explode=explode, labels=labels, colors=colors_pie,
            autopct='%1.0f%%', shadow=True, startangle=90, textprops={'fontsize': 11})
    ax2.set_title(f'Répartition des Features (Total: {n_feat_new})', 
                  fontsize=14, fontweight='bold')
    
    plt.tight_layout()
    plt.savefig(f"{OUTPUT_DIR}/model_comparison_summary.png", dpi=300)
    print(f"✅ Graphique sauvegardé: {OUTPUT_DIR}/model_comparison_summary.png")
    plt.close()

# ============================================
# MAIN
# ============================================

def main():
    print("=" * 80)
    print("📊 GÉNÉRATION DES VISUALISATIONS")
    print("=" * 80)
    print()
    
    print("1️⃣ Normales saisonnières...")
    plot_seasonal_normals()
    
    print("2️⃣ Variation durée du jour...")
    plot_day_length_variation()
    
    print("3️⃣ Importance des features...")
    plot_feature_importance()
    
    print("4️⃣ Encodage cyclique...")
    plot_cyclical_encoding()
    
    print("5️⃣ Comparaison des modèles...")
    plot_comparison_summary()
    
    print()
    print("=" * 80)
    print("✅ Toutes les visualisations ont été générées !")
    print("=" * 80)
    print(f"📁 Dossier: {OUTPUT_DIR}")
    print()
    print("Fichiers créés :")
    print("  - seasonal_normals.png")
    print("  - day_length_variation.png")
    print("  - seasonal_feature_importance.png")
    print("  - cyclical_encoding_explained.png")
    print("  - model_comparison_summary.png")
    print()

if __name__ == "__main__":
    main()
