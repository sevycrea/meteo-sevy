#!/bin/bash
# Script de vérification mensuelle - À exécuter le 1er de chaque mois
# Vérifie si assez de données pour passer au modèle saisonnier

METEO_DIR="/Users/yves/Desktop/Meteo_Backups"
DATA_FILE="${METEO_DIR}/data/json/meteo_data_enriched.json"
LOG_FILE="${METEO_DIR}/logs/monthly_check.log"

# Couleurs
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo "========================================================================"
echo "📅 VÉRIFICATION MENSUELLE - $(date '+%d %B %Y')"
echo "========================================================================"
echo ""

# Compter le nombre de jours de données
if [ -f "$DATA_FILE" ]; then
    # Compter les clés JSON (nombre de jours)
    NUM_DAYS=$(python3 -c "import json; data = json.load(open('$DATA_FILE')); print(len(data))")
    
    echo "📊 Données disponibles : $NUM_DAYS jours"
    echo ""
    
    # Calculer les mois approximatifs
    MONTHS=$((NUM_DAYS / 30))
    echo "📅 Environ $MONTHS mois de données"
    echo ""
    
    # Vérifier si prêt pour le modèle saisonnier
    if [ $NUM_DAYS -ge 365 ]; then
        echo -e "${GREEN}✅ PRÊT POUR LE MODÈLE SAISONNIER !${NC}"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo -e "${BLUE}🎉 Vous avez maintenant 1+ an de données${NC}"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "📈 Amélioration attendue avec le modèle saisonnier :"
        echo "   MAE : 0.48°C → 0.38-0.42°C (-12% à -21%)"
        echo ""
        echo "🚀 Actions recommandées :"
        echo ""
        echo "1️⃣  Réentraîner le modèle saisonnier :"
        echo "   cd ~/Desktop/Meteo_Backups"
        echo "   python3 scripts/train_model_seasonal.py"
        echo ""
        echo "2️⃣  Comparer les performances :"
        echo "   python3 scripts/compare_models.py"
        echo ""
        echo "3️⃣  Si amélioration > 5%, basculer vers le saisonnier :"
        echo "   launchctl unload ~/Library/LaunchAgents/com.sevy.meteo.predictions.plist"
        echo "   cp ~/Downloads/com_sevy_meteo_predictions_SEASONAL.plist \\"
        echo "      ~/Library/LaunchAgents/com.sevy.meteo.predictions.plist"
        echo "   launchctl load ~/Library/LaunchAgents/com.sevy.meteo.predictions.plist"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Envoyer une notification macOS
        osascript -e 'display notification "Vous avez 1+ an de données ! Temps de passer au modèle saisonnier." with title "Météo ML" sound name "Glass"'
        
    elif [ $NUM_DAYS -ge 330 ]; then
        echo -e "${YELLOW}⏳ BIENTÔT PRÊT ($NUM_DAYS/365 jours)${NC}"
        echo ""
        echo "📅 Il vous reste environ $((365 - NUM_DAYS)) jours de collecte"
        echo "🎯 Objectif : $(date -v+$((365 - NUM_DAYS))d '+%d %B %Y')"
        echo ""
        echo "💡 Continuez la collecte actuelle"
        echo "   Le système actuel (MAE 0.48°C) fonctionne très bien !"
        echo ""
        
    else
        echo -e "${BLUE}📊 Collecte en cours ($NUM_DAYS/365 jours)${NC}"
        echo ""
        echo "📅 Il vous reste environ $((365 - NUM_DAYS)) jours de collecte"
        echo "📈 Progression : $(( (NUM_DAYS * 100) / 365 ))%"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        
        # Barre de progression
        PROGRESS=$(( (NUM_DAYS * 50) / 365 ))
        BAR=$(printf "%${PROGRESS}s" | tr ' ' '█')
        EMPTY=$(printf "%$((50 - PROGRESS))s" | tr ' ' '░')
        echo "  [$BAR$EMPTY] $((NUM_DAYS * 100 / 365))%"
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        echo "✅ Système actuel optimal pour $NUM_DAYS jours de données"
        echo "🎯 Prochain check : 1er $(date -v+1m '+%B %Y')"
        echo ""
    fi
    
else
    echo "❌ Fichier de données introuvable : $DATA_FILE"
fi

echo "========================================================================"

# Logger
echo "[$(date)] Jours: $NUM_DAYS, Mois: $MONTHS" >> "$LOG_FILE"
