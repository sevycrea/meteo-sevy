# 🔧 Guide: Passer aux Données Horaires (24h Glissantes)

## 🎯 Objectif
Collecter les données **toutes les heures** pour afficher un graphique des **24 dernières heures réelles**.

---

## 📋 Étapes d'Installation

### **1️⃣ Installer le Nouveau Script Python**

```bash
# 1. Copier le nouveau script
cp auto_meteo_wunderground_hourly.py /Users/yves/Documents/Météo/scripts/

# 2. Configurer votre clé API (ligne 18)
nano /Users/yves/Documents/Météo/scripts/auto_meteo_wunderground_hourly.py

# Modifier:
API_KEY = "VOTRE_VRAIE_CLE_API"

# Et les credentials FTP (lignes 26-29) si besoin
```

---

### **2️⃣ Installer le Script Shell**

```bash
# 1. Copier le script shell
cp auto_wunderground_hourly.sh /Users/yves/Documents/Météo/scripts/

# 2. Rendre exécutable
chmod +x /Users/yves/Documents/Météo/scripts/auto_wunderground_hourly.sh

# 3. Vérifier le chemin de Python
which python3
# Ajuster le chemin dans le script shell si différent
```

---

### **3️⃣ Tester le Script Manuellement**

```bash
# Lancer le script
cd /Users/yves/Documents/Météo/scripts/
python3 auto_meteo_wunderground_hourly.py

# Vérifier que le JSON est créé
ls -lh /Users/yves/Documents/Météo/data/json/meteo_data_hourly.json

# Voir le contenu
cat /Users/yves/Documents/Météo/data/json/meteo_data_hourly.json | head -50
```

**Structure attendue :**
```json
{
  "2026-04-30": {
    "hourly": {
      "14:00": {
        "temp": 15.2,
        "hum": 65,
        "wind": 12.5,
        ...
      },
      "15:00": {
        "temp": 16.1,
        "hum": 62,
        ...
      }
    },
    "daily": {
      "temp_min": 8.5,
      "temp_max": 16.8,
      "temp_avg": 12.3,
      ...
    }
  }
}
```

---

### **4️⃣ Configurer le Cron (Toutes les Heures)**

```bash
# Éditer le cron
crontab -e

# Ajouter cette ligne (collecte à la minute 5 de chaque heure)
5 * * * * /Users/yves/Documents/Météo/scripts/auto_wunderground_hourly.sh >> /Users/yves/Documents/Météo/logs/cron_hourly.log 2>&1

# Vérifier
crontab -l
```

**Cela lancera le script à :**
- 00:05, 01:05, 02:05, ..., 23:05

---

### **5️⃣ Modifier le JavaScript**

Ouvrir `meteo-pro-script.js` et **remplacer** la fonction `initTrend24hChart()` par le contenu de `fonction_graphique_24h_reelles.js`

**Ligne à changer aussi** (environ ligne 50) :
```javascript
// AVANT
const jsonPath = wp_meteo_vars.theme_uri + '/Meteo/meteo_data.json';

// APRÈS (pour ce graphique uniquement, garder l'ancien pour le reste)
// Ou créer une nouvelle variable
```

**Mieux encore** : Utiliser les deux fichiers JSON
- `meteo_data.json` → Pour les graphiques quotidiens
- `meteo_data_hourly.json` → Pour le graphique 24h

---

### **6️⃣ Upload vers WordPress**

```bash
# Upload FTP manuel si nécessaire
# Ou le script le fera automatiquement

# Fichiers à uploader :
- meteo_data_hourly.json  → /wp-content/themes/astra-child/Meteo/
- meteo-pro-script.js      → /wp-content/themes/astra-child/
```

---

## 🕐 Calendrier de Collecte

### **Option 1 : Toutes les Heures (Recommandé)**
```bash
# À la minute 5 de chaque heure
5 * * * * script
```
→ 24 points par jour

### **Option 2 : Toutes les 30 Minutes**
```bash
# À 00 et 30 de chaque heure
0,30 * * * * script
```
→ 48 points par jour

### **Option 3 : Toutes les 15 Minutes**
```bash
# À 00, 15, 30, 45 de chaque heure
*/15 * * * * script
```
→ 96 points par jour

---

## 📊 Résultat Attendu

### **Graphique "Dernières 24h"** :
```
📈 Dernières 24 Heures
┌────────────────────────────────┐
│           ╱──╲                 │
│        ╱─╯    ╲─╮              │
│     ╱─╯          ╲─╮           │
│  ╱─╯                ╲──╮       │
│ ╱                      ╲─╮     │
└────────────────────────────────┘
14:05  18:05  22:05  02:05  06:05  10:05  14:05
Hier                               Aujourd'hui
```

**Données RÉELLES** collectées toutes les heures !

---

## 🔄 Transition Progressive

### **Phase 1 : Garder les Deux Systèmes**

Pendant la transition, vous pouvez **garder les deux** :
- Ancien script (toutes les 10 min) → `meteo_data.json`
- Nouveau script (toutes les heures) → `meteo_data_hourly.json`

Les graphiques quotidiens utilisent `meteo_data.json`.
Le graphique 24h utilise `meteo_data_hourly.json`.

### **Phase 2 : Fusionner (Optionnel)**

Après quelques semaines, fusionner en un seul système.

---

## ⚠️ Espace Disque

**Estimation** :
- 1 heure = ~200 octets JSON
- 24h = ~5 Ko
- 90 jours = ~450 Ko
- Avec backups = ~5 Mo

Très raisonnable ! ✅

---

## 🧪 Tests

### **Test 1 : Le script fonctionne**
```bash
python3 auto_meteo_wunderground_hourly.py
# Doit afficher: ✅ Collecte horaire terminée
```

### **Test 2 : Le JSON est correct**
```bash
cat meteo_data_hourly.json | python3 -m json.tool | head -30
# Doit afficher du JSON valide
```

### **Test 3 : Le cron fonctionne**
```bash
# Attendre 1h05, puis :
cat /Users/yves/Documents/Météo/logs/cron_hourly.log
# Doit contenir des logs
```

### **Test 4 : Le graphique affiche**
Recharger la page météo → Le graphique 24h doit afficher les vraies heures !

---

## ❓ Questions Fréquentes

### **Q: Ça va remplacer l'ancien système ?**
Non, vous pouvez garder les deux. L'ancien pour les stats quotidiennes, le nouveau pour le graphique 24h.

### **Q: Que se passe-t-il si le Mac est éteint ?**
Le cron ne s'exécute pas. Au redémarrage, il manquera quelques heures. Ce n'est pas grave, le graphique s'adaptera.

### **Q: Combien de temps avant d'avoir 24h de données ?**
24 heures ! Après 24h, le graphique sera complet.

### **Q: Puis-je changer la fréquence ?**
Oui, modifiez le cron. Mais attention : plus de fréquence = plus de points = graphique plus détaillé mais plus chargé.

---

## 🚀 Allons-y !

1. ✅ Téléchargez les 3 fichiers
2. ✅ Installez le script Python
3. ✅ Configurez le cron
4. ✅ Modifiez le JavaScript
5. ✅ Attendez 24h pour avoir un graphique complet

**C'est parti ! 🎯**
