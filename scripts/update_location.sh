#!/bin/bash
# Script de correction : Winterthur → Vinelz

echo "=========================================="
echo "🔧 Correction de la localisation"
echo "=========================================="
echo ""

BASE_DIR="/Users/yves/Desktop/Meteo_Backups"

# Liste des fichiers à modifier
FILES=(
    "$BASE_DIR/scripts/detect_events.py"
    "$BASE_DIR/scripts/export_to_ftp.py"
    "$BASE_DIR/web/index.html"
    "$BASE_DIR/web/alertes_meteo.html"
)

echo "📍 Changement : Winterthur → Vinelz"
echo ""

for file in "${FILES[@]}"; do
    if [ -f "$file" ]; then
        echo "✅ Modification de: $(basename $file)"
        # macOS nécessite '' après -i
        sed -i '' 's/Winterthur/Vinelz/g' "$file"
    else
        echo "⚠️  Fichier non trouvé: $(basename $file)"
    fi
done

echo ""
echo "=========================================="
echo "✅ Correction terminée !"
echo "=========================================="
echo ""
echo "📍 Nouvelle localisation : Vinelz, Suisse"
echo ""
