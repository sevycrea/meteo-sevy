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
from ftp_helpers import upload_data, upload_legacy
from io_helpers import atomic_write_json

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_FILE = os.path.join(BASE_DIR, "data", "sky.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "sky.log")

# Sources d'ensoleillement voisines (Vinelz n'a pas de capteur solaire) :
#  1) Station Weather Underground (API WU, fonctionne depuis le serveur)
#  2) Station Weathercloud (repli ; bloquée depuis les IP datacenter GitHub)
# NB : un secret GitHub absent est injecté comme chaîne VIDE (pas absent) →
# on utilise `or` pour retomber sur le défaut.
WU_API_KEY  = os.environ.get("WU_API_KEY", "")
# Stations WU voisines avec capteur solaire, par ordre de priorité (la 1re qui
# répond avec un rayonnement est utilisée). IINS23 = Ins, IGAMPE11 = Gampelen.
# IGAMPE11 (Gampelen) : capteur solaire fiable. IINS23 (Ins) écarté : son capteur
# lit ~0 W/m² même sous ciel clair (ombragé / en panne). Surchargeable par secret.
SKY_WU_IDS  = [s.strip() for s in (os.environ.get("SKY_STATION_ID") or "IGAMPE11").split(",") if s.strip()]
DEVICE      = os.environ.get("WEATHERCLOUD_DEVICE") or "8539205623"  # Jolimont, Erlach
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
LAT, LON = 47.0552, 7.1248  # Vinelz

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(os.path.dirname(OUT_FILE), exist_ok=True)


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')


_WU_PLACE = {"IINS23": "Ins", "IGAMPE11": "Gampelen"}

def fetch_wu():
    """Ensoleillement via Weather Underground (marche depuis le serveur).
    Essaie chaque station de SKY_WU_IDS jusqu'à en trouver une avec solaire."""
    if not WU_API_KEY:
        log("⚠️ WU_API_KEY absente — saut de la source WU")
        return None
    for sid in SKY_WU_IDS:
        url = (f"https://api.weather.com/v2/pws/observations/current?stationId={sid}"
               f"&format=json&units=m&numericPrecision=decimal&apiKey={WU_API_KEY}")
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=20)
            r.raise_for_status()
            obs_list = (r.json() or {}).get('observations') or []
        except Exception as e:
            log(f"⚠️ WU {sid} échec : {e}")
            continue
        if not obs_list or not isinstance(obs_list[0], dict):
            log(f"⚠️ WU {sid} : pas d'observation.")
            continue
        o = obs_list[0]
        solar = o.get('solarRadiation')
        if solar is None:
            log(f"⚠️ WU {sid} : pas de capteur solaire.")
            continue
        place = _WU_PLACE.get(sid, sid)
        log(f"☀️ WU {sid} ({place}) OK : solarRadiation={solar}, uv={o.get('uv')}")
        return {
            "solarrad": solar,
            "uvi": o.get('uv'),
            "epoch": o.get('epoch') or int(datetime.now(timezone.utc).timestamp()),
            "rainrate": (o.get('metric') or {}).get('precipRate'),
            "_src": f"{place} ({sid}, WU, ~3 km)",
        }
    return None


def fetch_weathercloud():
    url = f"https://app.weathercloud.net/device/values?code={DEVICE}"
    headers = {
        "X-Requested-With": "XMLHttpRequest",
        "Referer": f"https://app.weathercloud.net/d{DEVICE}",
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "fr-CH,fr;q=0.9,en;q=0.8",
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/124.0 Safari/537.36"),
    }
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    try:
        data = r.json()
    except Exception:
        log(f"⚠️ Réponse non-JSON (len={len(r.text)}): {r.text[:120]!r}")
        return None
    # Weathercloud peut renvoyer un dict (OK) ou une liste (vide = bloqué/limité).
    if isinstance(data, dict):
        return data
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return data[0]
        log(f"⚠️ Réponse liste inattendue (len={len(data)}) — accès probablement limité.")
        return None
    log(f"⚠️ Type de réponse inattendu: {type(data).__name__}")
    return None


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
    # 1) Weather Underground (fonctionne depuis le serveur GitHub)
    v = None
    try:
        v = fetch_wu()
    except Exception as e:
        log(f"⚠️ WU exception : {e}")
    # 2) Repli Weathercloud (souvent bloqué depuis datacenter, mais on tente)
    if not (isinstance(v, dict) and v.get('solarrad') is not None):
        try:
            wc = fetch_weathercloud()
            if isinstance(wc, dict) and wc.get('solarrad') is not None:
                wc['_src'] = "Jolimont, Erlach (Weathercloud, ~3 km)"
                v = wc
        except Exception as e:
            log(f"⚠️ Weathercloud exception : {e}")

    if not (isinstance(v, dict) and v.get('solarrad') is not None):
        log("⚠️ Aucune source solaire exploitable — sky.json non mis à jour (repli humidité côté clients).")
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
        "source": v.get('_src', "ensoleillement station voisine (~3 km)"),
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

    # Upload : legacy (FTP_*) = chemin réellement servi par data.sevy-creations.net,
    # + data (DATA_FTP_*) si le compte dédié est configuré. Comme le hourly.
    try:
        upload_legacy(OUT_FILE, 'sky.json', log=log)
        log("✅ sky.json uploadé (legacy)")
    except Exception as e:
        log(f"⚠️ Upload legacy sky.json échoué : {e}")
    try:
        upload_data(OUT_FILE, 'sky.json', log=log)
    except Exception as e:
        log(f"⚠️ Upload data sky.json échoué : {e}")

    return True


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
