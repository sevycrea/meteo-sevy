#!/usr/bin/env python3
"""
Nébulosité « temps réel » à partir de l'ENSOLEILLEMENT MESURÉ par une station
voisine équipée d'un capteur solaire : Jolimont, Erlach (Weathercloud), à ~3 km
de Vinelz, même micro-climat (Seeland / Trois-Lacs).

La station IVINEL2 (Vinelz) n'a pas de capteur solaire ; le cloud_cover du NWP
est une prévision peu fiable en direct. Ici on compare le rayonnement solaire
MESURÉ au rayonnement ciel-clair théorique (modèle Haurwitz) → indice de clarté
kt → état du ciel observé. C'est une mesure, pas un modèle.

Sortie : data/sky.json, uploadé sur data.sevy-creations.net/sky.json.
"""
import os
import sys
import math
import json
from datetime import datetime, timezone

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftp_helpers import upload_data
from io_helpers import atomic_write_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(BASE_DIR, "data", "sky.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "sky.log")

# Station Weathercloud de référence (device code). Surchargeable par env.
DEVICE = os.environ.get("WEATHERCLOUD_DEVICE", "8539205623")
LAT, LON = 47.0552, 7.1248  # Vinelz

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def fetch_values():
    url = f"https://app.weathercloud.net/device/values?code={DEVICE}"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://app.weathercloud.net/d{DEVICE}",
        "User-Agent": "Mozilla/5.0 (MeteoSevy sky fetch)",
    }
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json()


def sun_position(epoch):
    """Élévation solaire (degrés) + sin(h) à Vinelz pour un epoch UTC."""
    dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
    n = dt.timetuple().tm_yday
    decl = math.radians(23.45) * math.sin(math.radians(360 * (284 + n) / 365))
    frac = dt.hour + dt.minute / 60 + dt.second / 3600
    solar_time = frac + LON / 15.0
    H = math.radians(15 * (solar_time - 12))
    latr = math.radians(LAT)
    sinh = math.sin(latr) * math.sin(decl) + math.cos(latr) * math.cos(decl) * math.cos(H)
    sinh = max(-1.0, min(1.0, sinh))
    return math.degrees(math.asin(sinh)), max(0.0, sinh)


def classify(kt, is_day):
    """kt = rayonnement mesuré / ciel-clair. Retourne (condition, emoji)."""
    if not is_day:
        return "night", "🌙"
    if kt is None:
        return "unknown", "☀️"
    if kt >= 0.75:
        return "clear", "☀️"
    if kt >= 0.55:
        return "partly", "🌤️"
    if kt >= 0.35:
        return "cloudy", "⛅"
    return "overcast", "☁️"


def main():
    try:
        v = fetch_values()
    except Exception as e:
        log(f"❌ Lecture Weathercloud échouée : {e}")
        return False

    solar = v.get('solarrad')
    uv = v.get('uvi')
    rain_rate = v.get('rainrate')
    epoch = v.get('epoch') or int(datetime.now(timezone.utc).timestamp())

    h, cosZ = sun_position(epoch)
    is_day = h > 3.0
    ghi_clear = 1098 * cosZ * math.exp(-0.059 / cosZ) if cosZ > 0.02 else 0.0
    kt = (solar / ghi_clear) if (ghi_clear > 0 and solar is not None) else None
    if kt is not None:
        kt = max(0.0, min(1.2, kt))

    condition, icon = classify(kt, is_day)
    # Pluie active mesurée à Jolimont → on le signale (l'icône pluie reste gérée
    # côté client via le pluviomètre local, mais on publie l'info).
    raining = bool(rain_rate and rain_rate > 0)

    out = {
        "epoch": epoch,
        "updated": datetime.now(timezone.utc).isoformat(),
        "source": "Jolimont, Erlach (Weathercloud · ~3 km)",
        "solar_rad": solar,
        "uv": uv,
        "rain_rate": rain_rate,
        "raining": raining,
        "sun_elevation": round(h, 1),
        "clear_sky_ghi": round(ghi_clear),
        "clearness": round(kt, 2) if kt is not None else None,
        "is_day": is_day,
        "condition": condition,   # clear | partly | cloudy | overcast | night | unknown
        "icon": icon,
    }
    atomic_write_json(OUT_FILE, out)
    log(f"✅ ciel = {condition} {icon}  (kt={out['clearness']}, solar={solar} W/m², h={h:.0f}°)")

    try:
        upload_data(OUT_FILE, 'sky.json', log=log)
        log("✅ sky.json uploadé")
    except Exception as e:
        log(f"⚠️ Upload sky.json échoué : {e}")

    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
