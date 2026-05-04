#!/usr/bin/env python3
"""
Mise à jour des chemins dans tous les scripts après réorganisation
"""
import os
import re

BASE = "/Users/yves/Desktop/Meteo_Backups"
SCRIPTS_DIR = os.path.join(BASE, "scripts")

# Nouveaux chemins
NEW_PATHS = {
    'DATA_DIR': f'"{BASE}/data/csv"',
    'JSON_OUTPUT': f'os.path.join("{BASE}/data/json", "meteo_data.json")',
    'LOG_FILE': f'os.path.join("{BASE}/logs", "auto_update_wunderground.log")',
}

print("=" * 70)
print("🔄 MISE À JOUR DES CHEMINS DANS LES SCRIPTS")
print("=" * 70)

scripts_to_update = [
    'auto_meteo_wunderground.py',
    'generer_json_web_francais.py',
    'fusionner_donnees.py',
]

for script_name in scripts_to_update:
    script_path = os.path.join(SCRIPTS_DIR, script_name)
    
    if not os.path.exists(script_path):
        print(f"\n⚠️  {script_name} - Non trouvé")
        continue
    
    print(f"\n📝 {script_name}")
    
    with open(script_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    original_content = content
    
    # Remplacer DATA_DIR
    content = re.sub(
        r'DATA_DIR\s*=\s*"[^"]*"',
        f'DATA_DIR = "{BASE}/data/csv"',
        content
    )
    
    # Remplacer les chemins de fichiers JSON
    content = re.sub(
        r'JSON_OUTPUT\s*=\s*os\.path\.join\([^)]+\)',
        f'JSON_OUTPUT = os.path.join("{BASE}/data/json", "meteo_data.json")',
        content
    )
    
    content = re.sub(
        r'OUTPUT_JSON\s*=\s*os\.path\.join\([^)]+\)',
        f'OUTPUT_JSON = os.path.join("{BASE}/data/json", "meteo_data.json")',
        content
    )
    
    # Remplacer les chemins de logs
    content = re.sub(
        r'LOG_FILE\s*=\s*os\.path\.join\([^)]+auto_update[^)]+\)',
        f'LOG_FILE = os.path.join("{BASE}/logs", "auto_update_wunderground.log")',
        content
    )
    
    # Remplacer les chemins de backup
    content = re.sub(
        r'(JSON_OUTPUT|OUTPUT_JSON)\.replace\(\'\.json\',\s*f?\'_backup_',
        f'os.path.join("{BASE}/data/json/backup", "meteo_data_backup_',
        content
    )
    
    if content != original_content:
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"   ✅ Mis à jour")
    else:
        print(f"   ℹ️  Aucune modification nécessaire")

# Mettre à jour le script shell
shell_script = os.path.join(SCRIPTS_DIR, 'auto_wunderground.sh')
if os.path.exists(shell_script):
    print(f"\n📝 auto_wunderground.sh")
    
    with open(shell_script, 'r') as f:
        content = f.read()
    
    # Remplacer le chemin
    content = re.sub(
        r'cd /Users/yves/Desktop/Meteo_Backups/Data',
        f'cd {SCRIPTS_DIR}',
        content
    )
    
    with open(shell_script, 'w') as f:
        f.write(content)
    
    print(f"   ✅ Mis à jour")

print("\n" + "=" * 70)
print("✅ MISE À JOUR TERMINÉE")
print("=" * 70)
print(f"\n📂 Tous les scripts pointent maintenant vers :")
print(f"   - CSV     : {BASE}/data/csv/")
print(f"   - JSON    : {BASE}/data/json/")
print(f"   - Logs    : {BASE}/logs/")
print(f"   - Scripts : {BASE}/scripts/")
print("\n🎯 Prochaine étape : Mettre à jour le cron")
print(f"   crontab -e")
print(f"   Modifier : 0 1 * * * {SCRIPTS_DIR}/auto_wunderground.sh >> {BASE}/logs/cron.log 2>&1")
print("=" * 70)
