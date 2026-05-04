#!/bin/bash
#
# Migration vers structure organisée
# Réorganise le répertoire Météo
#

BASE="/Users/yves/Desktop/Meteo_Backups"

echo "======================================================================="
echo "📁 RÉORGANISATION DU RÉPERTOIRE MÉTÉO"
echo "======================================================================="

# Créer la nouvelle structure
echo ""
echo "📂 Création de la structure..."

mkdir -p "$BASE/data/csv"
mkdir -p "$BASE/data/json/backup"
mkdir -p "$BASE/scripts"
mkdir -p "$BASE/logs"
mkdir -p "$BASE/wordpress"

echo "   ✅ Dossiers créés"

# Déplacer les CSV
echo ""
echo "📥 Migration des fichiers CSV..."
mv "$BASE/Data/"*.csv "$BASE/data/csv/" 2>/dev/null && echo "   ✅ CSV déplacés" || echo "   ⚠️  Aucun CSV à déplacer"

# Déplacer le JSON actuel
echo ""
echo "📊 Migration du JSON..."
if [ -f "$BASE/Data/meteo_data.json" ]; then
    cp "$BASE/Data/meteo_data.json" "$BASE/data/json/meteo_data.json"
    echo "   ✅ JSON copié"
fi

# Déplacer les backups JSON
echo ""
echo "💾 Migration des backups..."
mv "$BASE/Data/meteo_data_backup_"*.json "$BASE/data/json/backup/" 2>/dev/null && echo "   ✅ Backups déplacés" || echo "   ⚠️  Aucun backup à déplacer"

# Déplacer les scripts Python
echo ""
echo "🐍 Migration des scripts Python..."
mv "$BASE/Data/"*.py "$BASE/scripts/" 2>/dev/null && echo "   ✅ Scripts Python déplacés" || echo "   ⚠️  Aucun script à déplacer"

# Déplacer les scripts shell
echo ""
echo "🔧 Migration des scripts shell..."
mv "$BASE/Data/"*.sh "$BASE/scripts/" 2>/dev/null && echo "   ✅ Scripts shell déplacés" || echo "   ⚠️  Aucun script à déplacer"

# Déplacer les logs
echo ""
echo "📝 Migration des logs..."
mv "$BASE/Data/"*.log "$BASE/logs/" 2>/dev/null && echo "   ✅ Logs déplacés" || echo "   ⚠️  Aucun log à déplacer"

# Déplacer les fichiers WordPress
echo ""
echo "🌐 Migration des fichiers WordPress..."
mv "$BASE/Data/page-meteo.php" "$BASE/wordpress/" 2>/dev/null
mv "$BASE/Data/meteo-"*.css "$BASE/wordpress/" 2>/dev/null
mv "$BASE/Data/meteo-"*.js "$BASE/wordpress/" 2>/dev/null
mv "$BASE/Data/functions-meteo-code.php" "$BASE/wordpress/" 2>/dev/null
echo "   ✅ Fichiers WordPress déplacés"

# Résumé
echo ""
echo "======================================================================="
echo "✅ MIGRATION TERMINÉE"
echo "======================================================================="
echo ""
echo "📁 Nouvelle structure :"
echo "   $BASE/"
echo "   ├── data/csv/          → Fichiers CSV"
echo "   ├── data/json/         → JSON et backups"
echo "   ├── scripts/           → Scripts Python et shell"
echo "   ├── logs/              → Fichiers de logs"
echo "   └── wordpress/         → Fichiers WordPress"
echo ""
echo "⚠️  L'ancien dossier 'Data' peut être supprimé après vérification"
echo ""
echo "🔄 Prochaine étape : Mettre à jour les chemins dans les scripts"
echo "   Lancez : cd $BASE/scripts && python3 mettre_a_jour_chemins.py"
echo "======================================================================="
