#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Calcul des Seuils Optimaux depuis les Données Historiques
Analyse les 270 jours de données pour calculer les normales et percentiles
"""

import json
import os
from datetime import datetime
import numpy as np
from collections import defaultdict

# ============================================
# CONFIGURATION
# ============================================

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_FILE = f"{BASE_DIR}/data/json/meteo_data_enriched.json"
OUTPUT_FILE = f"{BASE_DIR}/data/thresholds/adaptive_thresholds.json"
REPORT_FILE = f"{BASE_DIR}/data/thresholds/thresholds_report.txt"

os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Afficher et logger"""
    print(message)

def load_data():
    """Charger les données historiques"""
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        log(f"❌ Erreur chargement données: {e}")
        return None

def analyze_by_month(data):
    """Analyser les données par mois"""
    
    monthly_temps = defaultdict(list)
    monthly_rain = defaultdict(list)
    monthly_pressure = defaultdict(list)
    
    for date_str, day_data in data.items():
        try:
            date_obj = datetime.strptime(date_str, '%Y-%m-%d')
            month = date_obj.month
            
            # Température
            if 'temp_avg' in day_data:
                monthly_temps[month].append(day_data['temp_avg'])
            
            # Pluie
            if 'rain' in day_data:
                monthly_rain[month].append(day_data['rain'])
            
            # Pression
            if 'pressure_avg' in day_data:
                monthly_pressure[month].append(day_data['pressure_avg'])
                
        except:
            continue
    
    return monthly_temps, monthly_rain, monthly_pressure

def calculate_statistics(values):
    """Calculer statistiques complètes"""
    
    if not values or len(values) < 5:
        return None
    
    values = np.array(values)
    
    return {
        'mean': float(np.mean(values)),
        'std': float(np.std(values)),
        'min': float(np.min(values)),
        'max': float(np.max(values)),
        'median': float(np.median(values)),
        'p10': float(np.percentile(values, 10)),   # 10% plus bas
        'p25': float(np.percentile(values, 25)),   # Quartile inférieur
        'p75': float(np.percentile(values, 75)),   # Quartile supérieur
        'p90': float(np.percentile(values, 90)),   # 10% plus haut
        'p95': float(np.percentile(values, 95)),   # 5% plus haut (événement rare)
        'p99': float(np.percentile(values, 99)),   # 1% plus haut (très rare)
        'count': len(values)
    }

def generate_adaptive_thresholds(monthly_temps):
    """Générer seuils adaptatifs par mois"""
    
    thresholds = {}
    
    MONTH_NAMES = {
        1: 'Janvier', 2: 'Février', 3: 'Mars', 4: 'Avril',
        5: 'Mai', 6: 'Juin', 7: 'Juillet', 8: 'Août',
        9: 'Septembre', 10: 'Octobre', 11: 'Novembre', 12: 'Décembre'
    }
    
    for month in range(1, 13):
        if month not in monthly_temps:
            continue
        
        stats = calculate_statistics(monthly_temps[month])
        if not stats:
            continue
        
        mean = stats['mean']
        std = stats['std']
        
        # CHALEUR
        # Niveau 1 : +2 écarts-types (chaleur inhabituelle, ~2.5% des cas)
        # Niveau 2 : +3 écarts-types (canicule, ~0.1% des cas)
        heat_warning = mean + (2.0 * std)
        heat_critical = mean + (3.0 * std)
        
        # Alternative : utiliser percentiles directs
        heat_warning_p = stats['p95']  # 5% plus chaud
        heat_critical_p = stats['p99']  # 1% plus chaud
        
        # FROID
        # Niveau 1 : -2 écarts-types
        # Niveau 2 : -3 écarts-types
        cold_warning = mean - (2.0 * std)
        cold_critical = mean - (3.0 * std)
        
        cold_warning_p = stats['p10']  # 10% plus froid
        cold_critical_p = stats['p10'] - std  # Encore plus froid
        
        thresholds[month] = {
            'name': MONTH_NAMES[month],
            'statistics': stats,
            'temperature': {
                'heat': {
                    'warning': {
                        'sigma': round(heat_warning, 1),
                        'percentile': round(heat_warning_p, 1),
                        'recommended': round(max(heat_warning, heat_warning_p), 1)
                    },
                    'critical': {
                        'sigma': round(heat_critical, 1),
                        'percentile': round(heat_critical_p, 1),
                        'recommended': round(max(heat_critical, heat_critical_p), 1)
                    }
                },
                'cold': {
                    'warning': {
                        'sigma': round(cold_warning, 1),
                        'percentile': round(cold_warning_p, 1),
                        'recommended': round(min(cold_warning, cold_warning_p), 1)
                    },
                    'critical': {
                        'sigma': round(cold_critical, 1),
                        'percentile': 0.0,  # Point de congélation
                        'recommended': 0.0
                    }
                }
            }
        }
    
    return thresholds

def generate_report(thresholds, monthly_temps, monthly_rain, monthly_pressure):
    """Générer un rapport texte détaillé"""
    
    report = []
    report.append("=" * 80)
    report.append("RAPPORT D'ANALYSE DES SEUILS OPTIMAUX - VINELZ")
    report.append("=" * 80)
    report.append(f"Généré le : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append(f"Données analysées : {sum(len(v) for v in monthly_temps.values())} jours")
    report.append("")
    
    # Résumé annuel
    all_temps = []
    for temps in monthly_temps.values():
        all_temps.extend(temps)
    
    if all_temps:
        annual_stats = calculate_statistics(all_temps)
        report.append("RÉSUMÉ ANNUEL (VINELZ)")
        report.append("-" * 80)
        report.append(f"  Température moyenne :    {annual_stats['mean']:.1f}°C")
        report.append(f"  Écart-type :             {annual_stats['std']:.1f}°C")
        report.append(f"  Minimum observé :        {annual_stats['min']:.1f}°C")
        report.append(f"  Maximum observé :        {annual_stats['max']:.1f}°C")
        report.append(f"  Médiane :                {annual_stats['median']:.1f}°C")
        report.append("")
    
    # Détails par mois
    report.append("NORMALES ET SEUILS PAR MOIS")
    report.append("=" * 80)
    report.append("")
    
    for month in range(1, 13):
        if month not in thresholds:
            continue
        
        t = thresholds[month]
        stats = t['statistics']
        
        report.append(f"📅 {t['name'].upper()}")
        report.append("-" * 80)
        report.append(f"  Données : {stats['count']} jours")
        report.append("")
        report.append(f"  📊 STATISTIQUES")
        report.append(f"     Moyenne :             {stats['mean']:.1f}°C")
        report.append(f"     Écart-type :          {stats['std']:.1f}°C")
        report.append(f"     Min/Max observés :    {stats['min']:.1f}°C / {stats['max']:.1f}°C")
        report.append(f"     Médiane :             {stats['median']:.1f}°C")
        report.append("")
        report.append(f"  🌡️  SEUILS CHALEUR")
        report.append(f"     Avertissement :       {t['temperature']['heat']['warning']['recommended']:.1f}°C")
        report.append(f"                           (méthode σ: {t['temperature']['heat']['warning']['sigma']:.1f}°C, P95: {t['temperature']['heat']['warning']['percentile']:.1f}°C)")
        report.append(f"     Critique :            {t['temperature']['heat']['critical']['recommended']:.1f}°C")
        report.append(f"                           (méthode σ: {t['temperature']['heat']['critical']['sigma']:.1f}°C, P99: {t['temperature']['heat']['critical']['percentile']:.1f}°C)")
        report.append("")
        report.append(f"  ❄️  SEUILS FROID")
        report.append(f"     Avertissement :       {t['temperature']['cold']['warning']['recommended']:.1f}°C")
        report.append(f"                           (méthode σ: {t['temperature']['cold']['warning']['sigma']:.1f}°C, P10: {t['temperature']['cold']['warning']['percentile']:.1f}°C)")
        report.append(f"     Critique (gel) :      {t['temperature']['cold']['critical']['recommended']:.1f}°C")
        report.append("")
        
        # Interprétation
        report.append(f"  💡 INTERPRÉTATION")
        heat_warn = t['temperature']['heat']['warning']['recommended']
        heat_crit = t['temperature']['heat']['critical']['recommended']
        cold_warn = t['temperature']['cold']['warning']['recommended']
        
        report.append(f"     En {t['name']}, une température :")
        report.append(f"     • > {heat_warn:.1f}°C est inhabituelle (top 5%)")
        report.append(f"     • > {heat_crit:.1f}°C est extrême (top 1%)")
        report.append(f"     • < {cold_warn:.1f}°C est inhabituelle (bottom 10%)")
        report.append(f"     • < 0°C est un gel")
        report.append("")
        report.append("")
    
    # Comparaison anciens vs nouveaux seuils
    report.append("=" * 80)
    report.append("COMPARAISON : SEUILS ARBITRAIRES vs SEUILS OPTIMISÉS")
    report.append("=" * 80)
    report.append("")
    report.append("EXEMPLE : Juillet à Vinelz")
    report.append("-" * 80)
    
    if 7 in thresholds:
        july = thresholds[7]
        report.append(f"  Seuils ARBITRAIRES (anciens) :")
        report.append(f"     Chaleur :      30.0°C")
        report.append(f"     Canicule :     35.0°C")
        report.append("")
        report.append(f"  Seuils OPTIMISÉS (nouveaux, basés sur vos données) :")
        report.append(f"     Chaleur :      {july['temperature']['heat']['warning']['recommended']:.1f}°C")
        report.append(f"     Canicule :     {july['temperature']['heat']['critical']['recommended']:.1f}°C")
        report.append("")
        
        diff_warn = july['temperature']['heat']['warning']['recommended'] - 30.0
        diff_crit = july['temperature']['heat']['critical']['recommended'] - 35.0
        
        report.append(f"  📊 DIFFÉRENCES :")
        report.append(f"     Seuil chaleur :   {diff_warn:+.1f}°C")
        report.append(f"     Seuil canicule :  {diff_crit:+.1f}°C")
        report.append("")
        
        if diff_warn > 0:
            report.append(f"  💡 À Vinelz en juillet, 30°C est PLUS FROID que la normale inhabituelle.")
            report.append(f"     → Les anciens seuils déclencheraient trop d'alertes (faux positifs)")
        else:
            report.append(f"  💡 À Vinelz en juillet, 30°C est déjà inhabituel.")
            report.append(f"     → Les anciens seuils sont appropriés")
    
    report.append("")
    report.append("=" * 80)
    report.append("FIN DU RAPPORT")
    report.append("=" * 80)
    
    return "\n".join(report)

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 80)
    log("📊 CALCUL DES SEUILS OPTIMAUX DEPUIS VOS DONNÉES")
    log("=" * 80)
    log("")
    
    # Charger données
    log("📂 Chargement des données...")
    data = load_data()
    if not data:
        return
    
    log(f"✅ {len(data)} jours chargés")
    log("")
    
    # Analyser par mois
    log("📊 Analyse par mois...")
    monthly_temps, monthly_rain, monthly_pressure = analyze_by_month(data)
    log(f"✅ Données réparties sur {len(monthly_temps)} mois")
    log("")
    
    # Calculer seuils adaptatifs
    log("🔨 Calcul des seuils adaptatifs...")
    thresholds = generate_adaptive_thresholds(monthly_temps)
    log(f"✅ Seuils calculés pour {len(thresholds)} mois")
    log("")
    
    # Générer rapport
    log("📝 Génération du rapport...")
    report = generate_report(thresholds, monthly_temps, monthly_rain, monthly_pressure)
    
    # Sauvegarder JSON
    output = {
        'generated_at': datetime.now().isoformat(),
        'location': 'Vinelz, Suisse',
        'data_period': {
            'start': min(data.keys()),
            'end': max(data.keys()),
            'days': len(data)
        },
        'thresholds': thresholds
    }
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    log(f"✅ Seuils sauvegardés : {OUTPUT_FILE}")
    
    # Sauvegarder rapport
    with open(REPORT_FILE, 'w', encoding='utf-8') as f:
        f.write(report)
    
    log(f"✅ Rapport sauvegardé : {REPORT_FILE}")
    log("")
    
    # Afficher aperçu
    log("=" * 80)
    log("📊 APERÇU DES RÉSULTATS")
    log("=" * 80)
    log("")
    
    # Afficher quelques mois clés
    for month in [1, 4, 7, 10]:  # Janvier, Avril, Juillet, Octobre
        if month in thresholds:
            t = thresholds[month]
            log(f"{t['name']} :")
            log(f"  Moyenne : {t['statistics']['mean']:.1f}°C")
            log(f"  Seuil chaleur : {t['temperature']['heat']['warning']['recommended']:.1f}°C")
            log(f"  Seuil canicule : {t['temperature']['heat']['critical']['recommended']:.1f}°C")
            log("")
    
    log("=" * 80)
    log("✅ ANALYSE TERMINÉE")
    log("=" * 80)
    log("")
    log(f"📁 Consultez le rapport complet : {REPORT_FILE}")
    log("")

if __name__ == "__main__":
    main()
