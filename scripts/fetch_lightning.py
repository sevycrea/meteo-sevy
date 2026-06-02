#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_lightning.py — Détection d'orage via Blitzortung (backend GitHub Actions).

Écoute la WebSocket temps réel de Blitzortung (wss/443, format compressé décodé
en interne), puis publie sur data.sevy-creations.net :
  • lightning.json — résumé orage autour de VINELZ (app Météo Sevy + site).
  • strikes.json   — éclairs récents de la RÉGION (CH + voisins), fenêtre 60 min,
                     pour l'app OrageDetection (distance calculée côté app selon
                     la position GPS de l'utilisateur).

Conforme Blitzortung : c'est NOTRE serveur qui sert NOS clients, l'app/le site
ne touchent jamais Blitzortung directement.
"""
import asyncio
import json
import math
import os
import random
import ssl
import sys
import tempfile
import time
import ftplib
import urllib.request
from datetime import datetime, timezone

# --- Vinelz (lightning.json) ---
VINELZ_LAT = 47.0552
VINELZ_LON = 7.1248
RADIUS_KM = float(os.environ.get("RADIUS_KM", "30"))
PUBLIC_URL = "https://data.sevy-creations.net/lightning.json"

# --- Région (strikes.json pour OrageDetection) : Suisse + France + Allemagne + Italie ---
REGION = {"lat_min": 35.0, "lat_max": 55.5, "lon_min": -5.5, "lon_max": 19.0}
STRIKES_URL = "https://data.sevy-creations.net/strikes.json"
STRIKES_MAX_AGE = 3600   # garder 60 min d'historique
STRIKES_MAX = 8000       # plafond de points (4 pays = beaucoup d'éclairs)

LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "270"))
SERVERS = [1, 2, 3, 7, 8]

FTP_HOST = os.environ.get("FTP_HOST") or os.environ.get("DATA_FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER") or os.environ.get("DATA_FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS") or os.environ.get("DATA_FTP_PASS", "")


def log(m):
    print(f"[{datetime.now():%H:%M:%S}] {m}", flush=True)


def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def bo_decode(s):
    """Décompresse le format « maison » de Blitzortung (variante LZW) → JSON."""
    d = {}
    c = list(s)
    if not c:
        return s
    f = c[0]
    g = f
    out = [f]
    p = 256
    for i in range(1, len(c)):
        code = ord(c[i])
        a = c[i] if 256 > code else d.get(code, g + f)
        out.append(a)
        f = a[0]
        d[p] = g + f
        p += 1
        g = a
    return "".join(out)


def parse_message(raw):
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    try:
        return json.loads(raw)
    except Exception:
        try:
            return json.loads(bo_decode(raw))
        except Exception:
            return None


async def listen():
    import websockets

    near = []            # (epoch, distance_km) proches de Vinelz
    region = []          # [epoch, lat, lon] dans la région
    total_msgs = 0
    total_strikes = 0
    last_err = None

    for sid in random.sample(SERVERS, len(SERVERS)):
        uri = f"wss://ws{sid}.blitzortung.org/"   # port 443
        try:
            async with websockets.connect(
                uri, open_timeout=15, ping_interval=20, ping_timeout=20, max_size=None
            ) as ws:
                await ws.send(json.dumps({"a": 111}))
                log(f"connecté à {uri} — écoute {LISTEN_SECONDS}s")
                end = time.monotonic() + LISTEN_SECONDS
                tried_alt = False
                while time.monotonic() < end:
                    remaining = end - time.monotonic()
                    if remaining <= 0:
                        break
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 10))
                    except asyncio.TimeoutError:
                        if not tried_alt and total_msgs == 0:
                            await ws.send(json.dumps({"time": 0}))
                            tried_alt = True
                            continue
                        if total_msgs == 0:
                            break
                        continue
                    total_msgs += 1
                    obj = parse_message(raw)
                    if not isinstance(obj, dict):
                        continue
                    lat, lon = obj.get("lat"), obj.get("lon")
                    if lat is None or lon is None:
                        continue
                    try:
                        flat, flon = float(lat), float(lon)
                    except Exception:
                        continue
                    total_strikes += 1
                    t_ns = obj.get("time") or 0
                    epoch = (t_ns / 1e9) if t_ns else time.time()
                    # région (app OrageDetection)
                    if (REGION["lat_min"] <= flat <= REGION["lat_max"]
                            and REGION["lon_min"] <= flon <= REGION["lon_max"]):
                        region.append([round(epoch), round(flat, 4), round(flon, 4)])
                    # proche de Vinelz (lightning.json)
                    if haversine_km(VINELZ_LAT, VINELZ_LON, flat, flon) <= RADIUS_KM:
                        near.append((epoch, haversine_km(VINELZ_LAT, VINELZ_LON, flat, flon)))
            if total_msgs > 0:
                break
        except Exception as e:
            last_err = e
            log(f"échec {uri}: {type(e).__name__} {e}")
            continue

    log(f"reçu {total_msgs} msg · {total_strikes} éclairs · "
        f"{len(near)} proches Vinelz · {len(region)} dans la région")
    if total_msgs == 0 and last_err:
        log(f"⚠️ aucune donnée (dernier err: {last_err})")
    return near, region


def previous_nearest():
    try:
        with urllib.request.urlopen(PUBLIC_URL + "?t=" + str(int(time.time())), timeout=10) as r:
            return json.load(r).get("nearest_km")
    except Exception:
        return None


def build_lightning(near):
    now = datetime.now(timezone.utc)
    if not near:
        return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "calme",
                "severity": "none", "nearest_km": None, "strike_count": 0,
                "window_min": round(LISTEN_SECONDS / 60, 1), "trend": None, "last_strike_at": None}
    nearest = round(min(d for _, d in near), 1)
    last_epoch = max(e for e, _ in near)
    severity = "critical" if nearest < 10 else "warning" if nearest < 20 else "info"
    prev = previous_nearest()
    trend = None
    if isinstance(prev, (int, float)):
        trend = "approche" if nearest < prev - 2 else "eloigne" if nearest > prev + 2 else "stable"
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "status": "orage",
            "severity": severity, "nearest_km": nearest, "strike_count": len(near),
            "window_min": round(LISTEN_SECONDS / 60, 1), "trend": trend,
            "last_strike_at": datetime.fromtimestamp(last_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}


def build_strikes(region):
    """Fusionne les nouveaux éclairs régionaux avec l'existant (fenêtre glissante 60 min)."""
    now = datetime.now(timezone.utc)
    existing = []
    try:
        with urllib.request.urlopen(STRIKES_URL + "?t=" + str(int(time.time())), timeout=10) as r:
            existing = json.load(r).get("strikes", [])
    except Exception:
        existing = []
    cutoff = time.time() - STRIKES_MAX_AGE
    merged = [s for s in existing if isinstance(s, list) and len(s) == 3 and s[0] >= cutoff]
    merged += region
    merged.sort(key=lambda s: s[0])
    if len(merged) > STRIKES_MAX:
        merged = merged[-STRIKES_MAX:]
    return {"generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"), "region": REGION,
            "window_min": STRIKES_MAX_AGE // 60, "count": len(merged), "strikes": merged}


def upload_json(payload, name, summary):
    if not (FTP_HOST and FTP_USER and FTP_PASS):
        log(f"⚠️ FTP creds manquants — {name} non uploadé ({summary})")
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
        tmp = f.name
    ctx = ssl.create_default_context()
    with ftplib.FTP_TLS(context=ctx) as ftp:
        ftp.connect(FTP_HOST, 21, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.prot_p()
        with open(tmp, "rb") as fh:
            ftp.storbinary(f"STOR {name}.tmp", fh)
        try:
            ftp.delete(name)
        except ftplib.error_perm:
            pass
        ftp.rename(f"{name}.tmp", name)
    os.unlink(tmp)
    log(f"✅ {name} uploadé ({summary})")


def main():
    near, region = asyncio.run(listen())
    lightning = build_lightning(near)
    strikes = build_strikes(region)
    upload_json(lightning, "lightning.json", lightning["status"] + " nearest=" + str(lightning["nearest_km"]))
    upload_json(strikes, "strikes.json", f"{strikes['count']} éclairs / {strikes['window_min']} min")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ Erreur : {e}")
        sys.exit(1)
