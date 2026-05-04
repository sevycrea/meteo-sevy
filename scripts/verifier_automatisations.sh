#!/bin/bash
# ============================================================================
# SCRIPT DE VÉRIFICATION DES AUTOMATISATIONS MÉTÉO
# ============================================================================
# Usage: ./verifier_automatisations.sh
# ============================================================================

echo ""
echo "╔════════════════════════════════════════════════════════════════╗"
echo "║   🔍 VÉRIFICATION DES AUTOMATISATIONS MÉTÉO                   ║"
echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

METEO_DIR="$HOME/Desktop/Meteo_Backups"
ALL_OK=true

# ============================================================================
# 1. VÉRIFIER LES TÂCHES LAUNCHD
# ============================================================================

echo "📋 1. TÂCHES LAUNCHD"
echo "────────────────────────────────────────────────────────────────"

TASKS=$(launchctl list | grep sevy 2>/dev/null)

if [ -z "$TASKS" ]; then
    echo "❌ Aucune tâche launchd trouvée !"
    echo "   → Les tâches ne sont pas chargées"
    echo ""
    ALL_OK=false
else
    echo "$TASKS" | while read line; do
        PID=$(echo "$line" | awk '{print $1}')
        STATUS=$(echo "$line" | awk '{print $2}')
        LABEL=$(echo "$line" | awk '{print $3}')
        
        if [ "$STATUS" = "0" ]; then
            echo "✅ $LABEL - Status: OK"
        else
            echo "⚠️  $LABEL - Status: $STATUS (erreur)"
        fi
    done
    echo ""
fi

# ============================================================================
# 2. VÉRIFIER LES FICHIERS DE DONNÉES
# ============================================================================

echo "📊 2. FICHIERS DE DONNÉES"
echo "────────────────────────────────────────────────────────────────"

cd "$METEO_DIR/data/json/" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "❌ Dossier data/json/ non trouvé !"
    echo ""
    ALL_OK=false
else
    # Vérifier meteo_data.json
    if [ -f "meteo_data.json" ]; then
        MOD_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" meteo_data.json)
        SIZE=$(stat -f "%z" meteo_data.json)
        SIZE_KB=$((SIZE / 1024))
        
        # Calculer l'âge du fichier
        MOD_TIMESTAMP=$(stat -f "%m" meteo_data.json)
        NOW_TIMESTAMP=$(date +%s)
        AGE_SECONDS=$((NOW_TIMESTAMP - MOD_TIMESTAMP))
        AGE_HOURS=$((AGE_SECONDS / 3600))
        
        if [ $AGE_HOURS -lt 2 ]; then
            echo "✅ meteo_data.json"
            echo "   Dernière mise à jour: $MOD_TIME (il y a ${AGE_HOURS}h)"
            echo "   Taille: ${SIZE_KB} KB"
        else
            echo "⚠️  meteo_data.json"
            echo "   Dernière mise à jour: $MOD_TIME (il y a ${AGE_HOURS}h !)"
            echo "   → Devrait être mis à jour toutes les heures"
            ALL_OK=false
        fi
    else
        echo "❌ meteo_data.json non trouvé"
        ALL_OK=false
    fi
    echo ""
    
    # Vérifier predictions.json
    if [ -f "predictions.json" ]; then
        MOD_TIME=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" predictions.json)
        SIZE=$(stat -f "%z" predictions.json)
        SIZE_KB=$((SIZE / 1024))
        
        echo "✅ predictions.json"
        echo "   Dernière mise à jour: $MOD_TIME"
        echo "   Taille: ${SIZE_KB} KB"
    else
        echo "⚠️  predictions.json non trouvé"
    fi
    echo ""
fi

# ============================================================================
# 3. VÉRIFIER LES LOGS
# ============================================================================

echo "📝 3. LOGS DES SCRIPTS"
echo "────────────────────────────────────────────────────────────────"

cd "$METEO_DIR/logs/" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "❌ Dossier logs/ non trouvé !"
    echo ""
    ALL_OK=false
else
    # Log collecte horaire
    if [ -f "launchd_hourly.log" ]; then
        echo "📄 Collecte horaire (5 dernières lignes) :"
        tail -5 launchd_hourly.log | sed 's/^/   /'
        echo ""
        
        # Vérifier s'il y a des erreurs récentes
        ERRORS=$(tail -20 launchd_hourly.log | grep -c "❌")
        if [ $ERRORS -gt 0 ]; then
            echo "⚠️  $ERRORS erreur(s) dans les 20 dernières lignes"
            ALL_OK=false
        fi
    else
        echo "⚠️  launchd_hourly.log non trouvé"
    fi
    echo ""
    
    # Log prédictions
    if [ -f "predictions.log" ]; then
        echo "📄 Prévisions (3 dernières lignes) :"
        tail -3 predictions.log | sed 's/^/   /'
    else
        echo "⚠️  predictions.log non trouvé"
    fi
    echo ""
fi

# ============================================================================
# 4. INFORMATIONS TEMPORELLES
# ============================================================================

echo "⏰ 4. INFORMATIONS TEMPORELLES"
echo "────────────────────────────────────────────────────────────────"

CURRENT_TIME=$(date '+%H:%M')
CURRENT_MIN=$(date '+%M')
CURRENT_HOUR=$(date '+%H')

echo "Heure actuelle      : $CURRENT_TIME"
echo ""

# Prochaine collecte horaire
NEXT_COLLECTION_HOUR=$CURRENT_HOUR
if [ $CURRENT_MIN -ge 5 ]; then
    NEXT_COLLECTION_HOUR=$(printf "%02d" $((10#$CURRENT_HOUR + 1)))
    if [ $NEXT_COLLECTION_HOUR -eq 24 ]; then
        NEXT_COLLECTION_HOUR="00"
    fi
fi

echo "Prochaines exécutions prévues :"
echo "  📥 Collecte       : ${NEXT_COLLECTION_HOUR}:05"
echo "  🎓 Entraînement   : 02:00 (quotidien)"
echo "  🔮 Prédictions    : 06:00 (quotidien)"
echo ""

# ============================================================================
# 5. RÉSUMÉ FINAL
# ============================================================================

echo "╔════════════════════════════════════════════════════════════════╗"

if [ "$ALL_OK" = true ]; then
    echo "║   ✅ TOUT FONCTIONNE CORRECTEMENT                             ║"
else
    echo "║   ⚠️  PROBLÈMES DÉTECTÉS - VOIR CI-DESSUS                     ║"
fi

echo "╚════════════════════════════════════════════════════════════════╝"
echo ""

# ============================================================================
# COMMANDES UTILES
# ============================================================================

echo "💡 COMMANDES UTILES :"
echo "────────────────────────────────────────────────────────────────"
echo ""
echo "Surveiller en temps réel :"
echo "  tail -f $METEO_DIR/logs/launchd_hourly.log"
echo ""
echo "Recharger les tâches :"
echo "  launchctl load ~/Library/LaunchAgents/com.sevy.meteo.hourly.plist"
echo ""
echo "Lancer manuellement :"
echo "  cd $METEO_DIR"
echo "  python3 scripts/auto_meteo_wunderground_hourly.py"
echo ""

exit 0
