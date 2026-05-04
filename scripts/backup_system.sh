#!/bin/bash
# Script de Backup Complet du Système Météo ML

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$HOME/Desktop/Meteo_Backups"
BACKUP_NAME="meteo_system_${TIMESTAMP}"
BACKUP_PATH="${BACKUP_DIR}/${BACKUP_NAME}"

echo "=========================================================================="
echo "💾 BACKUP COMPLET DU SYSTÈME MÉTÉO ML"
echo "=========================================================================="
echo ""
echo "📅 Date : $(date '+%Y-%m-%d %H:%M:%S')"
echo "📁 Destination : ${BACKUP_PATH}.tar.gz"
echo ""

# Créer le dossier de backup
mkdir -p "$BACKUP_DIR"
mkdir -p "$BACKUP_PATH"

# ============================================
# 1. SCRIPTS
# ============================================

echo "📂 Backup des scripts..."
if [ -d "$HOME/Desktop/Meteo_Backups/scripts" ]; then
    cp -R "$HOME/Desktop/Meteo_Backups/scripts" "$BACKUP_PATH/"
    echo "   ✅ Scripts sauvegardés"
else
    echo "   ⚠️  Dossier scripts non trouvé"
fi

# ============================================
# 2. DONNÉES
# ============================================

echo "📊 Backup des données..."
if [ -d "$HOME/Desktop/Meteo_Backups/data" ]; then
    # Sauvegarder seulement les fichiers importants (pas les gros modèles)
    mkdir -p "$BACKUP_PATH/data"
    
    # JSON
    if [ -d "$HOME/Desktop/Meteo_Backups/data/json" ]; then
        cp -R "$HOME/Desktop/Meteo_Backups/data/json" "$BACKUP_PATH/data/"
    fi
    
    # Events
    if [ -d "$HOME/Desktop/Meteo_Backups/data/events" ]; then
        cp -R "$HOME/Desktop/Meteo_Backups/data/events" "$BACKUP_PATH/data/"
    fi
    
    # Validation
    if [ -d "$HOME/Desktop/Meteo_Backups/data/validation" ]; then
        cp -R "$HOME/Desktop/Meteo_Backups/data/validation" "$BACKUP_PATH/data/"
    fi
    
    # Reports
    if [ -d "$HOME/Desktop/Meteo_Backups/data/reports" ]; then
        cp -R "$HOME/Desktop/Meteo_Backups/data/reports" "$BACKUP_PATH/data/"
    fi
    
    # Thresholds
    if [ -d "$HOME/Desktop/Meteo_Backups/data/thresholds" ]; then
        cp -R "$HOME/Desktop/Meteo_Backups/data/thresholds" "$BACKUP_PATH/data/"
    fi
    
    echo "   ✅ Données sauvegardées"
else
    echo "   ⚠️  Dossier data non trouvé"
fi

# ============================================
# 3. LAUNCHAGENTS
# ============================================

echo "⚙️  Backup des LaunchAgents..."
mkdir -p "$BACKUP_PATH/LaunchAgents"

for plist in ~/Library/LaunchAgents/com.sevy.meteo.*.plist; do
    if [ -f "$plist" ]; then
        cp "$plist" "$BACKUP_PATH/LaunchAgents/"
        echo "   ✅ $(basename $plist)"
    fi
done

# ============================================
# 4. WEB
# ============================================

echo "🌐 Backup des fichiers web..."
if [ -d "$HOME/Desktop/Meteo_Backups/web" ]; then
    cp -R "$HOME/Desktop/Meteo_Backups/web" "$BACKUP_PATH/"
    echo "   ✅ Fichiers web sauvegardés"
fi

# ============================================
# 5. LOGS (Derniers 7 jours seulement)
# ============================================

echo "📝 Backup des logs récents..."
if [ -d "$HOME/Desktop/Meteo_Backups/logs" ]; then
    mkdir -p "$BACKUP_PATH/logs"
    
    # Copier seulement les logs des 7 derniers jours
    find "$HOME/Desktop/Meteo_Backups/logs" -name "*.log" -mtime -7 -exec cp {} "$BACKUP_PATH/logs/" \;
    
    log_count=$(ls -1 "$BACKUP_PATH/logs" 2>/dev/null | wc -l)
    echo "   ✅ $log_count fichiers de logs sauvegardés"
fi

# ============================================
# 6. DOCUMENTATION
# ============================================

echo "📚 Backup de la documentation..."
if [ -d "$HOME/Desktop/Meteo_Backups" ]; then
    # Copier tous les fichiers MD
    find "$HOME/Desktop/Meteo_Backups" -maxdepth 2 -name "*.md" -exec cp {} "$BACKUP_PATH/" \;
    
    md_count=$(ls -1 "$BACKUP_PATH"/*.md 2>/dev/null | wc -l)
    echo "   ✅ $md_count fichiers de documentation sauvegardés"
fi

# ============================================
# 7. MÉTADONNÉES
# ============================================

echo "📋 Génération des métadonnées..."

# Créer un fichier de métadonnées
cat > "$BACKUP_PATH/BACKUP_INFO.txt" << EOF
========================================================================
BACKUP SYSTÈME MÉTÉO ML - VINELZ
========================================================================

Date du backup : $(date '+%Y-%m-%d %H:%M:%S')
Utilisateur : $(whoami)
Machine : $(hostname)

========================================================================
CONTENU DU BACKUP
========================================================================

Scripts :
$(ls -1 "$BACKUP_PATH/scripts" 2>/dev/null | wc -l) fichiers

Données :
- JSON : $(du -sh "$BACKUP_PATH/data/json" 2>/dev/null | cut -f1)
- Events : $(du -sh "$BACKUP_PATH/data/events" 2>/dev/null | cut -f1)
- Validation : $(du -sh "$BACKUP_PATH/data/validation" 2>/dev/null | cut -f1)
- Reports : $(du -sh "$BACKUP_PATH/data/reports" 2>/dev/null | cut -f1)

LaunchAgents :
$(ls -1 "$BACKUP_PATH/LaunchAgents" 2>/dev/null | wc -l) fichiers

Web :
$(du -sh "$BACKUP_PATH/web" 2>/dev/null | cut -f1)

Logs récents :
$(ls -1 "$BACKUP_PATH/logs" 2>/dev/null | wc -l) fichiers

Documentation :
$(ls -1 "$BACKUP_PATH"/*.md 2>/dev/null | wc -l) fichiers

========================================================================
STATISTIQUES
========================================================================

Jours de données : $(cat "$BACKUP_PATH/data/json/meteo_data_enriched.json" 2>/dev/null | python3 -c "import json, sys; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "N/A")

LaunchAgents actifs :
$(launchctl list | grep meteo | wc -l)

Taille totale backup :
$(du -sh "$BACKUP_PATH" | cut -f1)

========================================================================
RESTAURATION
========================================================================

Pour restaurer ce backup :

1. Extraire l'archive :
   tar -xzf ${BACKUP_NAME}.tar.gz

2. Copier les scripts :
   cp -R ${BACKUP_NAME}/scripts/* ~/Desktop/Meteo_Backups/scripts/

3. Copier les données :
   cp -R ${BACKUP_NAME}/data/* ~/Desktop/Meteo_Backups/data/

4. Restaurer les LaunchAgents :
   cp ${BACKUP_NAME}/LaunchAgents/*.plist ~/Library/LaunchAgents/
   launchctl load ~/Library/LaunchAgents/com.sevy.meteo.*.plist

========================================================================
FIN DU FICHIER INFO
========================================================================
EOF

echo "   ✅ Métadonnées générées"

# ============================================
# 8. COMPRESSION
# ============================================

echo ""
echo "📦 Compression de l'archive..."

cd "$BACKUP_DIR"
tar -czf "${BACKUP_NAME}.tar.gz" "$BACKUP_NAME"

# Supprimer le dossier temporaire
rm -rf "$BACKUP_PATH"

# Taille finale
BACKUP_SIZE=$(du -sh "${BACKUP_NAME}.tar.gz" | cut -f1)

echo "   ✅ Archive créée"
echo ""

# ============================================
# 9. RÉSUMÉ
# ============================================

echo "=========================================================================="
echo "✅ BACKUP TERMINÉ AVEC SUCCÈS"
echo "=========================================================================="
echo ""
echo "📁 Fichier : ${BACKUP_NAME}.tar.gz"
echo "📍 Emplacement : $BACKUP_DIR"
echo "💾 Taille : $BACKUP_SIZE"
echo ""
echo "=========================================================================="
echo "VÉRIFICATION"
echo "=========================================================================="
echo ""

# Lister le contenu de l'archive
echo "Contenu de l'archive :"
tar -tzf "${BACKUP_NAME}.tar.gz" | head -20
echo "   ... (voir archive complète pour la liste complète)"
echo ""

echo "=========================================================================="
echo "PROCHAINES ÉTAPES"
echo "=========================================================================="
echo ""
echo "1. ✅ Vérifiez que l'archive est présente sur votre Bureau"
echo "2. ✅ Testez l'extraction si vous voulez vérifier :"
echo "      tar -xzf ~/Desktop/Meteo_Backups/${BACKUP_NAME}.tar.gz -C /tmp"
echo "3. ✅ Conservez cette archive en lieu sûr"
echo "4. ✅ Vous pouvez maintenant migrer vers Claude Code"
echo ""
echo "=========================================================================="

# Ouvrir le dossier dans le Finder
open "$BACKUP_DIR"
