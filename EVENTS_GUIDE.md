# 🌡️ Détection d'Événements Météo - Guide Complet

## 🎯 Objectif

Recevoir des **alertes automatiques** pour les événements météo extrêmes avec **notifications macOS**.

---

## 📦 Ce que vous recevez

1. **detect_events.py** - Script de détection intelligent
2. **com.sevy.meteo.events.plist** - LaunchAgent (2×/jour : 6h30, 18h30)

---

## 🚀 Installation Rapide

```bash
# 1. Copier le script
cp ~/Downloads/detect_events.py ~/Documents/Météo/scripts/
chmod +x ~/Documents/Météo/scripts/detect_events.py

# 2. Copier le LaunchAgent
cp ~/Downloads/com.sevy.meteo.events.plist ~/Library/LaunchAgents/

# 3. Charger
launchctl load ~/Library/LaunchAgents/com.sevy.meteo.events.plist

# 4. Tester immédiatement
python3 ~/Documents/Météo/scripts/detect_events.py
```

---

## 🌡️ Événements Détectés

### 1. **Vague de Chaleur** 🔥

| Niveau | Seuil | Notification |
|--------|-------|--------------|
| **Chaleur** | > 30°C | 🌡️ Son: Glass |
| **Canicule Extrême** | > 35°C | 🔥 Son: Basso |

**Recommandations automatiques :**
- Restez au frais
- Hydratez-vous
- Évitez l'exposition au soleil

---

### 2. **Vague de Froid / Gel** ❄️

| Niveau | Seuil | Notification |
|--------|-------|--------------|
| **Gel** | < 0°C (min) | 🧊 Son: Glass |
| **Grand Froid** | < -10°C | ❄️ Son: Basso |

**Recommandations automatiques :**
- Protégez les plantes
- Attention au verglas
- Protégez les canalisations

---

### 3. **Pluie Forte** 🌧️

| Niveau | Seuil | Notification |
|--------|-------|--------------|
| **Pluie Forte** | Probabilité > 80% | 🌧️ Son: Glass |

**Recommandations automatiques :**
- Prévoyez un parapluie
- Possibles inondations locales

---

### 4. **Chute de Température** 📉

| Niveau | Seuil | Notification |
|--------|-------|--------------|
| **Chute Brutale** | > 10°C en 24h | 📉 Son: Purr |

**Recommandations automatiques :**
- Adaptez vos vêtements

---

## 🔔 Exemples de Notifications

### Canicule
```
┌─────────────────────────────────────┐
│  🔥 CANICULE EXTRÊME               │
│                                     │
│  35.2°C prévu Demain.              │
│  Restez au frais !                 │
│                                     │
│  [Son: Basso]                      │
└─────────────────────────────────────┘
```

### Gel
```
┌─────────────────────────────────────┐
│  🧊 Risque de Gel                  │
│                                     │
│  Minimum -2.1°C prévu Demain       │
│                                     │
│  [Son: Glass]                      │
└─────────────────────────────────────┘
```

### Chute de Température
```
┌─────────────────────────────────────┐
│  📉 Chute de Température           │
│                                     │
│  -12.5°C prévu Demain              │
│                                     │
│  [Son: Purr]                       │
└─────────────────────────────────────┘
```

---

## 📅 Automatisation

### Horaires de Détection

- **Matin : 6h30** - Alertes pour la journée
- **Soir : 18h30** - Alertes pour lendemain

**Pourquoi 2×/jour ?**
- Matin → Préparer la journée
- Soir → Anticiper le lendemain

---

## 📊 Exemple d'Exécution

```
========================================================================
🔍 DÉTECTION D'ÉVÉNEMENTS MÉTÉO
========================================================================
📅 Analyse de 3 prévisions

🧊 ALERTE GEL: -1.2°C le 2026-11-15
📉 ALERTE CHUTE TEMPÉRATURE: -11.3°C vers le 2026-11-16

========================================================================
📊 RÉSUMÉ
========================================================================
⚠️  2 alerte(s) détectée(s)

🟠 Alertes AVERTISSEMENT: 1
   🧊 Risque de GEL : minimum -1.2°C prévu Demain
🔵 Alertes INFO: 1
   📉 Chute de température : -11.3°C entre aujourd'hui et Après-demain

========================================================================
```

---

## 📂 Fichiers Générés

```
~/Documents/Météo/
├── data/
│   └── events/
│       └── alerts_history.json    ← Historique des alertes (100 dernières)
│
└── logs/
    ├── events.log                 ← Log des détections
    └── events_error.log           ← Erreurs éventuelles
```

---

## 🔍 Consulter l'Historique

### Voir toutes les alertes

```bash
cat ~/Documents/Météo/data/events/alerts_history.json | python3 -m json.tool | less
```

### Compter les alertes

```bash
python3 -c "import json; h = json.load(open('/Users/yves/Documents/Météo/data/events/alerts_history.json')); print(f'Total alertes: {len(h)}')"
```

### Voir les alertes récentes

```bash
tail -20 ~/Documents/Météo/logs/events.log
```

---

## ⚙️ Personnaliser les Seuils

Éditez `detect_events.py` pour ajuster les seuils :

```python
THRESHOLDS = {
    'heat_wave': {
        'temp_high': 28.0,      # Baisser à 28°C si vous êtes sensible
        'temp_very_high': 33.0,
    },
    'cold_wave': {
        'temp_low': 2.0,        # Alerter à 2°C au lieu de 0°C
        'temp_very_low': -5.0,
    },
    # ... etc
}
```

---

## 🔕 Désactiver les Notifications

### Temporairement

```bash
# Désactiver
launchctl unload ~/Library/LaunchAgents/com.sevy.meteo.events.plist

# Réactiver
launchctl load ~/Library/LaunchAgents/com.sevy.meteo.events.plist
```

### Garder la détection sans notifs

Éditez `detect_events.py` et commentez :

```python
# send_notification(...)  ← Commenter ces lignes
```

Les alertes seront toujours loggées mais sans notifications sonores.

---

## 📊 Statistiques

### Alertes par Type

```python
# Script Python pour analyser l'historique
import json
from collections import Counter

with open('/Users/yves/Documents/Météo/data/events/alerts_history.json') as f:
    alerts = json.load(f)

types = Counter(a['type'] for a in alerts)
for alert_type, count in types.most_common():
    print(f"{alert_type}: {count}")
```

---

## 🎯 Cas d'Usage

### Scénario 1 : Hiver

```
🔔 6h30 - Alerte gel pour aujourd'hui
→ Vous protégez les plantes avant de partir au travail

🔔 18h30 - Grand froid prévu demain (-12°C)
→ Vous préparez des vêtements chauds
```

### Scénario 2 : Été

```
🔔 6h30 - Canicule prévue (33°C)
→ Vous planifiez de rester au frais

🔔 18h30 - Canicule extrême demain (36°C)
→ Vous annulez votre sortie de midi
```

### Scénario 3 : Automne

```
🔔 6h30 - Chute de 15°C prévue demain
→ Vous préparez des vêtements adaptés

🔔 18h30 - Pluie forte probable (90%)
→ Vous prenez votre parapluie le lendemain
```

---

## 🔧 Dépannage

### Les notifications n'apparaissent pas

```bash
# Vérifier les permissions macOS
# Préférences Système → Notifications → Terminal
# Activer "Autoriser les notifications"

# Tester manuellement
osascript -e 'display notification "Test" with title "Météo" sound name "Glass"'
```

### Le script ne s'exécute pas

```bash
# Vérifier les logs
tail -20 ~/Documents/Météo/logs/events_error.log

# Tester manuellement
python3 ~/Documents/Météo/scripts/detect_events.py
```

### Le LaunchAgent n'est pas actif

```bash
# Vérifier
launchctl list | grep meteo

# Recharger
launchctl unload ~/Library/LaunchAgents/com.sevy.meteo.events.plist
launchctl load ~/Library/LaunchAgents/com.sevy.meteo.events.plist
```

---

## 💡 Améliorations Futures Possibles

### Alertes par Email

Ajouter l'envoi d'emails pour événements critiques.

### Alertes Personnalisées

Ajouter vos propres seuils (ex: allergies aux pollens quand > 20°C au printemps).

### Intégration Slack/Discord

Envoyer les alertes sur votre channel préféré.

---

## 🎓 Résumé

✅ **Installation :** 5 minutes  
✅ **Automatique :** 2×/jour (6h30, 18h30)  
✅ **Notifications :** macOS avec son  
✅ **Historique :** 100 dernières alertes  
✅ **Personnalisable :** Seuils ajustables  

**Résultat :** Vous êtes **toujours alerté** des événements météo extrêmes ! 🔔

---

**Version :** 1.0  
**Date :** 3 mai 2026  
**Prochaine alerte :** Demain 6h30
