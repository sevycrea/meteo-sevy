# 📅 Système de Rappel Automatique - Guide d'Installation

## 🎯 Objectif

Recevoir une **notification automatique** le 1er de chaque mois pour savoir quand vous avez assez de données (12+ mois) pour basculer vers le modèle saisonnier.

---

## 🚀 Installation Rapide

```bash
# 1. Copier le script de vérification
cp ~/Downloads/monthly_check.sh ~/Documents/Météo/scripts/
chmod +x ~/Documents/Météo/scripts/monthly_check.sh

# 2. Copier le LaunchAgent
cp ~/Downloads/com.sevy.meteo.monthlycheck.plist ~/Library/LaunchAgents/

# 3. Charger le LaunchAgent
launchctl load ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist

# 4. Tester immédiatement (sans attendre le 1er du mois)
launchctl start com.sevy.meteo.monthlycheck
```

---

## 📋 Ce que fait le système

### **Chaque 1er du mois à 9h du matin :**

1. ✅ Compte le nombre de jours de données collectées
2. ✅ Calcule le nombre de mois approximatifs
3. ✅ Évalue si vous êtes prêt pour le modèle saisonnier

### **Si vous avez 365+ jours (12+ mois) :**

- 🔔 **Notification macOS** vous alertant
- 📊 **Instructions détaillées** dans le terminal
- 📈 **Amélioration attendue** affichée
- 🚀 **Commandes exactes** pour basculer

### **Si vous avez 330-364 jours (11+ mois) :**

- ⏳ Message "BIENTÔT PRÊT"
- 📅 Nombre de jours restants
- 🎯 Date estimée pour atteindre 365 jours

### **Si vous avez < 330 jours :**

- 📊 Message de progression avec barre visuelle
- 📈 Pourcentage de complétion
- ✅ Confirmation que le système actuel est optimal

---

## 🧪 Tester Maintenant

```bash
# Exécuter le script manuellement
bash ~/Documents/Météo/scripts/monthly_check.sh
```

**Résultat attendu (avec vos 271 jours actuels) :**

```
========================================================================
📅 VÉRIFICATION MENSUELLE - 03 mai 2026
========================================================================

📊 Données disponibles : 271 jours

📅 Environ 9 mois de données

📊 Collecte en cours (271/365 jours)

📅 Il vous reste environ 94 jours de collecte
📈 Progression : 74%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  [█████████████████████████████████████░░░░░░░░░░░░░░] 74%
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ Système actuel optimal pour 271 jours de données
🎯 Prochain check : 1er juin 2026

========================================================================
```

---

## 📅 Calendrier Prévisionnel

Avec vos **271 jours actuels** (3 mai 2026) :

| Date | Jours | Status | Action |
|------|-------|--------|--------|
| **1er juin 2026** | ~302 | 📊 Collecte en cours (83%) | Continuer |
| **1er juillet 2026** | ~332 | ⏳ Bientôt prêt (91%) | Continuer |
| **1er août 2026** | ~363 | ⏳ Presque prêt (99%) | Se préparer |
| **1er sept. 2026** | **~394** | **✅ PRÊT !** | **BASCULER** 🎉 |

---

## 🔔 Notification macOS

Quand vous aurez 365+ jours, vous verrez apparaître :

```
┌─────────────────────────────────────┐
│  🔔 Météo ML                       │
│                                     │
│  Vous avez 1+ an de données !      │
│  Temps de passer au modèle         │
│  saisonnier.                       │
│                                     │
│  [Détails dans Terminal]           │
└─────────────────────────────────────┘
```

---

## 📊 Vérification Manuelle

Si vous voulez vérifier sans attendre le 1er du mois :

```bash
# Vérifier combien de jours vous avez
python3 -c "import json; data = json.load(open('/Users/yves/Documents/Météo/data/json/meteo_data_enriched.json')); print(f'Jours: {len(data)}')"

# Exécuter le check complet
bash ~/Documents/Météo/scripts/monthly_check.sh
```

---

## 🔍 Logs

Le système garde une trace de chaque vérification :

```bash
# Voir l'historique
cat ~/Documents/Météo/logs/monthly_check.log

# Exemple :
# [2026-05-01 09:00:02] Jours: 271, Mois: 9
# [2026-06-01 09:00:01] Jours: 302, Mois: 10
# [2026-07-01 09:00:03] Jours: 332, Mois: 11
# [2026-08-01 09:00:02] Jours: 363, Mois: 12
# [2026-09-01 09:00:01] Jours: 394, Mois: 13 ← PRÊT !
```

---

## ⚙️ Configuration

### Modifier la fréquence

Par défaut : **1er de chaque mois à 9h**

Pour changer :

```bash
# Éditer le .plist
nano ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist

# Modifier :
<key>Day</key>
<integer>1</integer>      ← Jour du mois (1-31)
<key>Hour</key>
<integer>9</integer>      ← Heure (0-23)

# Recharger
launchctl unload ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist
launchctl load ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist
```

### Désactiver les notifications

```bash
# Éditer le script
nano ~/Documents/Météo/scripts/monthly_check.sh

# Commenter la ligne :
# osascript -e 'display notification...'
```

---

## 🎯 Checklist d'Installation

- [ ] Script copié dans `~/Documents/Météo/scripts/`
- [ ] Script rendu exécutable (`chmod +x`)
- [ ] LaunchAgent copié dans `~/Library/LaunchAgents/`
- [ ] LaunchAgent chargé (`launchctl load`)
- [ ] Test manuel effectué (`launchctl start`)
- [ ] Vérification que le LaunchAgent est actif (`launchctl list | grep monthly`)

---

## 🚀 Commandes de Maintenance

```bash
# Vérifier que le LaunchAgent est chargé
launchctl list | grep monthly

# Forcer l'exécution immédiate (test)
launchctl start com.sevy.meteo.monthlycheck

# Voir le dernier résultat
tail -20 ~/Documents/Météo/logs/monthly_check.log

# Désactiver temporairement
launchctl unload ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist

# Réactiver
launchctl load ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist
```

---

## 📞 Dépannage

### Le LaunchAgent ne se charge pas

```bash
# Vérifier la syntaxe du .plist
plutil ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist

# Recharger avec verbose
launchctl load -w ~/Library/LaunchAgents/com.sevy.meteo.monthlycheck.plist
```

### Pas de notification

```bash
# Vérifier que le script a les bonnes permissions
ls -l ~/Documents/Météo/scripts/monthly_check.sh

# Tester la notification manuellement
osascript -e 'display notification "Test" with title "Météo ML"'
```

### Le script ne s'exécute pas

```bash
# Vérifier les logs d'erreur
tail -20 ~/Documents/Météo/logs/monthly_check_error.log

# Exécuter manuellement pour voir l'erreur
bash ~/Documents/Météo/scripts/monthly_check.sh
```

---

## 🎓 Résumé

✅ **Installation :** 2 minutes  
✅ **Automatique :** Vérification le 1er de chaque mois  
✅ **Notification :** Alert macOS quand prêt (365+ jours)  
✅ **Transparent :** Logs détaillés de chaque vérification  
✅ **Pratique :** Instructions complètes pour basculer  

**Résultat :** Vous saurez **exactement** quand passer au modèle saisonnier pour obtenir la meilleure précision ! 🎯

---

**Version :** 1.0  
**Date :** 3 mai 2026  
**Prochaine vérification :** 1er juin 2026
