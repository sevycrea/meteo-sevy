#!/usr/bin/env python3
"""
Script de diagnostic Weather Underground
Pour comprendre pourquoi les valeurs sont à 0
"""
import requests
import json
from datetime import datetime

WU_API_KEY = "de1b65ccc1fd4d6d9b65ccc1fded6d93"
WU_STATION_ID = "IVINEL2"
WU_API_URL = "https://api.weather.com/v2/pws/observations/all/1day"

print("=" * 70)
print("🔍 DIAGNOSTIC WEATHER UNDERGROUND")
print("=" * 70)

# Récupération des données
params = {
    'stationId': WU_STATION_ID,
    'format': 'json',
    'units': 'm',
    'apiKey': WU_API_KEY,
    'numericPrecision': 'decimal'
}

print(f"\n📡 Connexion à l'API...")
print(f"Station: {WU_STATION_ID}")

response = requests.get(WU_API_URL, params=params, timeout=30)

print(f"Status HTTP: {response.status_code}")

if response.status_code != 200:
    print(f"❌ Erreur API: {response.text}")
    exit(1)

data = response.json()

# Sauvegarder la réponse complète
with open('/Users/yves/Desktop/Meteo_Backups/Data/wu_debug_response.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f"💾 Réponse complète sauvegardée: wu_debug_response.json")

# Analyser les observations
if 'observations' not in data:
    print(f"\n❌ Pas de clé 'observations' dans la réponse!")
    print(f"Clés présentes: {list(data.keys())}")
    exit(1)

observations = data['observations']
print(f"\n📊 Nombre d'observations: {len(observations)}")

if len(observations) == 0:
    print("❌ AUCUNE OBSERVATION RETOURNÉE!")
    print("Votre station n'envoie peut-être plus de données à Wunderground")
    exit(1)

# Analyser la première observation
print("\n" + "=" * 70)
print("🔍 ANALYSE PREMIÈRE OBSERVATION")
print("=" * 70)

obs = observations[0]

print(f"\n📅 Epoch: {obs.get('epoch')}")
if obs.get('epoch'):
    dt = datetime.fromtimestamp(int(obs['epoch']))
    print(f"   Date/Heure: {dt.strftime('%Y-%m-%d %H:%M:%S')}")

print(f"\n🌡️  TEMPÉRATURE:")
metric = obs.get('metric', {})
print(f"   obs['metric']: {metric}")
print(f"   temp: {metric.get('temp')}")

print(f"\n💧 HUMIDITÉ:")
print(f"   obs['humidity']: {obs.get('humidity')}")

print(f"\n💨 VENT:")
print(f"   windSpeed: {metric.get('windSpeed')}")
print(f"   windGust: {metric.get('windGust')}")

print(f"\n🌧️  PLUIE:")
print(f"   precipRate: {metric.get('precipRate')}")
print(f"   precipTotal: {metric.get('precipTotal')}")

print(f"\n📊 PRESSION:")
print(f"   pressure: {metric.get('pressure')}")

# Afficher la structure complète de la première observation
print("\n" + "=" * 70)
print("📋 STRUCTURE COMPLÈTE PREMIÈRE OBSERVATION")
print("=" * 70)
print(json.dumps(obs, indent=2))

# Analyser toutes les observations
print("\n" + "=" * 70)
print("📊 ANALYSE DE TOUTES LES OBSERVATIONS")
print("=" * 70)

temps = []
humidities = []
wind_speeds = []

for i, obs in enumerate(observations):
    epoch = obs.get('epoch')
    if not epoch:
        continue
    
    dt = datetime.fromtimestamp(int(epoch))
    metric = obs.get('metric', {})
    
    temp = metric.get('temp')
    humidity = obs.get('humidity')
    wind_speed = metric.get('windSpeed')
    
    if temp is not None:
        temps.append(float(temp))
    if humidity is not None:
        humidities.append(float(humidity))
    if wind_speed is not None:
        wind_speeds.append(float(wind_speed))
    
    if i < 5:  # Afficher les 5 premières
        print(f"\nObs {i+1} - {dt.strftime('%Y-%m-%d %H:%M')}")
        print(f"  Temp: {temp}°C, Hum: {humidity}%, Vent: {wind_speed} km/h")

print("\n" + "=" * 70)
print("📈 STATISTIQUES")
print("=" * 70)

print(f"\n🌡️  Températures collectées: {len(temps)}")
if temps:
    print(f"   Min: {min(temps)}°C")
    print(f"   Max: {max(temps)}°C")
    print(f"   Moy: {sum(temps)/len(temps):.1f}°C")
else:
    print("   ⚠️  AUCUNE TEMPÉRATURE COLLECTÉE!")

print(f"\n💧 Humidités collectées: {len(humidities)}")
if humidities:
    print(f"   Moy: {sum(humidities)/len(humidities):.1f}%")
else:
    print("   ⚠️  AUCUNE HUMIDITÉ COLLECTÉE!")

print(f"\n💨 Vitesses vent collectées: {len(wind_speeds)}")
if wind_speeds:
    print(f"   Moy: {sum(wind_speeds)/len(wind_speeds):.1f} km/h")
else:
    print("   ⚠️  AUCUNE VITESSE DE VENT COLLECTÉE!")

print("\n" + "=" * 70)
print("✅ DIAGNOSTIC TERMINÉ")
print("=" * 70)
print("\nFichiers créés:")
print("  - wu_debug_response.json (réponse complète de l'API)")
print("\nProchaines étapes:")
print("  1. Vérifiez wu_debug_response.json")
print("  2. Regardez si les valeurs sont présentes dans la réponse")
print("  3. Vérifiez sur wunderground.com si votre station envoie des données")