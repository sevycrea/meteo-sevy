#!/usr/bin/env python3
"""
Fusion des données CSV + Weather Underground
Comble les trous de données
"""
import json
import os

BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_DIR = os.path.join(BASE_DIR, "data/csv")
JSON_OUTPUT = os.path.join(BASE_DIR, "data/json/meteo_data.json")
JSON_BACKUP = os.path.join(BASE_DIR, "data/json/backup/meteo_data_avant_fusion.json")

print("=" * 70)
print("🔄 FUSION DES DONNÉES")
print("=" * 70)

# 1. Sauvegarder le JSON actuel (avec les données WU du 30 avril)
print("\n💾 Sauvegarde du JSON actuel...")
if os.path.exists(JSON_OUTPUT):
    import shutil
    shutil.copy2(JSON_OUTPUT, JSON_BACKUP)
    print(f"   ✅ Backup créé : meteo_data_avant_fusion.json")
    
    # Charger le JSON actuel
    with open(JSON_OUTPUT, 'r', encoding='utf-8') as f:
        current_data = json.load(f)
else:
    current_data = {}

print(f"   📊 Données actuelles : {len(current_data)} jours")

# 2. Générer les données depuis les CSV
print("\n📥 Génération depuis les CSV...")
print("   Lancement de generer_json_web.py...")

import subprocess
result = subprocess.run(
    ['python3', 'generer_json_web_francais.py'],
    cwd=os.path.join(BASE_DIR, "scripts"),
    capture_output=True,
    text=True
)

if result.returncode != 0:
    print(f"   ❌ Erreur : {result.stderr}")
    exit(1)

print("   ✅ CSV traités")

# 3. Charger les données CSV
with open(JSON_OUTPUT, 'r', encoding='utf-8') as f:
    csv_data = json.load(f)

print(f"   📊 Données CSV : {len(csv_data)} jours")

# 4. Fusionner intelligemment
print("\n🔄 Fusion des données...")

# Stratégie : 
# - Garder les données CSV pour les dates anciennes
# - Garder les données WU pour les dates récentes (30 avril)

merged_data = {}

# Ajouter toutes les données CSV
for date_key, data in csv_data.items():
    merged_data[date_key] = data

# Écraser avec les données WU actuelles (plus fiables pour les dates récentes)
for date_key, data in current_data.items():
    # Si c'est une date récente (avril 2026) ET qu'elle vient de WU (valeurs non nulles)
    if date_key >= "2026-04-20":
        # Vérifier que ce ne sont pas que des 0
        if data['temp_max'] > 0 or data['temp_min'] > 0:
            merged_data[date_key] = data
            print(f"   ✅ Données WU conservées pour {date_key}")

# 5. Sauvegarder le résultat fusionné
print(f"\n💾 Sauvegarde du JSON fusionné...")

with open(JSON_OUTPUT, 'w', encoding='utf-8') as f:
    json.dump(merged_data, f, ensure_ascii=False, indent=2, sort_keys=True)

size_kb = os.path.getsize(JSON_OUTPUT) / 1024
print(f"   ✅ JSON sauvegardé : {size_kb:.1f} Ko")

# 6. Résumé
print("\n" + "=" * 70)
print("📊 RÉSUMÉ")
print("=" * 70)

dates = sorted(merged_data.keys())
print(f"\n📅 Période couverte : {dates[0]} → {dates[-1]}")
print(f"📊 Nombre total de jours : {len(merged_data)}")

# Vérifier les trous
from datetime import datetime, timedelta
start = datetime.strptime(dates[0], '%Y-%m-%d')
end = datetime.strptime(dates[-1], '%Y-%m-%d')
expected_days = (end - start).days + 1

if len(merged_data) < expected_days:
    print(f"⚠️  Il manque {expected_days - len(merged_data)} jour(s)")
    
    # Trouver les dates manquantes
    current = start
    missing = []
    while current <= end:
        date_str = current.strftime('%Y-%m-%d')
        if date_str not in merged_data:
            missing.append(date_str)
        current += timedelta(days=1)
    
    if missing:
        print(f"   Dates manquantes : {', '.join(missing[:10])}")
        if len(missing) > 10:
            print(f"   ... et {len(missing) - 10} autres")
else:
    print("✅ Aucun trou dans les données !")

print("\n" + "=" * 70)
print("✅ FUSION TERMINÉE")
print("=" * 70)
print("\nFichiers créés:")
print(f"  - {JSON_OUTPUT} (données fusionnées)")
print(f"  - {JSON_BACKUP} (backup avant fusion)")
