#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_lightning.py — Détection d'orage autour de Vinelz via Blitzortung.

Tourne dans GitHub Actions (le mutualisé Infomaniak bloque les ports data de
Blitzortung). Se connecte à la WebSocket temps réel de Blitzortung, écoute
~quelques minutes, garde les impacts dans un rayon autour de Vinelz, et écrit
`lightning.json` sur data.sevy-creations.net (FTPS).

L'app et le site lisent `lightning.json` (jamais Blitzortung directement) →
conforme à la politique non-commerciale de Blitzortung (serveur intermédiaire).
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

VINELZ_LAT = 47.0552
VINELZ_LON = 7.1248
RADIUS_KM = float(os.environ.get("RADIUS_KM", "30"))
LISTEN_SECONDS = int(os.environ.get("LISTEN_SECONDS", "270"))
SERVERS = [1, 2, 3, 7, 8]
PUBLIC_URL = "https://data.sevy-creations.net/lightning.json"

FTP_HOST = os.environ.get("DATA_FTP_HOST", "")
FTP_USER = os.environ.get("DATA_FTP_USER", "")
FTP_PASS = os.environ.get("DATA_FTP_PASS", "")


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
    """Décompresse le format « maison » de Blitzortung (variante LZW) → JSON.
    Repli si les messages ne sont pas du JSON brut."""
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
        if 256 > code:
            a = c[i]
        else:
            a = d.get(code, g + f)
        out.append(a)
        f = a[0]
        d[p] = g + f
        p += 1
        g = a
    return "".join(out)


def parse_message(raw):
    if isinstance(raw, (bytes, bytearray)):
        raw = raw.decode("utf-8", "replace")
    for candidate in (raw, None):
        try:
            return json.loads(raw if candidate is raw else bo_decode(raw))
        except Exception:
            continue
    return None


async def listen():
    import websockets

    strikes = []        # (epoch_s, distance_km)
    total_msgs = 0
    total_strikes = 0
    last_err = None
    samples = []

    for sid in random.sample(SERVERS, len(SERVERS)):
        uri = f"wss://ws{sid}.blitzortung.org/"   # port 443 (joignable partout)
        try:
            async with websockets.connect(
                uri, open_timeout=15, ping_interval=20, ping_timeout=20, max_size=None
            ) as ws:
                await ws.send(json.dumps({"a": 111}))
                log(f"connecté à {uri} (subscribe a:111) — écoute {LISTEN_SECONDS}s")
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
                            log('aucun message — tentative subscribe {"time":0}')
                            continue
                        if total_msgs == 0:
                            break
                        continue
                    total_msgs += 1
                    if len(samples) < 3:
                        s = raw if isinstance(raw, str) else raw.decode("utf-8", "replace")
                        samples.append(s[:160])
                    obj = parse_message(raw)
                    if not isinstance(obj, dict):
                        continue
                    lat, lon = obj.get("lat"), obj.get("lon")
                    if lat is None or lon is None:
                        continue
                    total_strikes += 1
                    try:
                        dist = haversine_km(VINELZ_LAT, VINELZ_LON, float(lat), float(lon))
                    except Exception:
                        continue
                    if dist <= RADIUS_KM:
                        t_ns = obj.get("time") or 0
                        epoch = (t_ns / 1e9) if t_ns else time.time()
                        strikes.append((epoch, dist))
            if total_msgs > 0:
                break  # un serveur a fourni des données, on arrête
        except Exception as e:
            last_err = e
            log(f"échec {uri}: {type(e).__name__} {e}")
            continue

    for i, s in enumerate(samples):
        log(f"  sample[{i}]: {s!r}")
    log(f"reçu {total_msgs} messages · {total_strikes} éclairs (monde) · "
        f"{len(strikes)} dans {RADIUS_KM:.0f} km de Vinelz")
    if total_msgs == 0 and last_err:
        log(f"⚠️ aucune donnée (dernier err: {last_err})")
    return strikes


def previous_nearest():
    try:
        with urllib.request.urlopen(PUBLIC_URL + "?t=" + str(int(time.time())), timeout=10) as r:
            prev = json.load(r)
        return prev.get("nearest_km")
    except Exception:
        return None


def build_payload(strikes):
    now = datetime.now(timezone.utc)
    count = len(strikes)
    if count == 0:
        return {
            "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "status": "calme",
            "severity": "none",
            "nearest_km": None,
            "strike_count": 0,
            "window_min": round(LISTEN_SECONDS / 60, 1),
            "trend": None,
            "last_strike_at": None,
        }
    nearest = round(min(d for _, d in strikes), 1)
    last_epoch = max(e for e, _ in strikes)
    severity = "critical" if nearest < 10 else "warning" if nearest < 20 else "info"
    prev = previous_nearest()
    trend = None
    if isinstance(prev, (int, float)):
        if nearest < prev - 2:
            trend = "approche"
        elif nearest > prev + 2:
            trend = "eloigne"
        else:
            trend = "stable"
    return {
        "generated_at": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": "orage",
        "severity": severity,
        "nearest_km": nearest,
        "strike_count": count,
        "window_min": round(LISTEN_SECONDS / 60, 1),
        "trend": trend,
        "last_strike_at": datetime.fromtimestamp(last_epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def upload(payload):
    if not (FTP_HOST and FTP_USER and FTP_PASS):
        log("⚠️ FTP creds manquants — pas d'upload (dry-run)")
        log(json.dumps(payload, ensure_ascii=False))
        return
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
        tmp = f.name
    ctx = ssl.create_default_context()
    with ftplib.FTP_TLS(context=ctx) as ftp:
        ftp.connect(FTP_HOST, 21, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)
        ftp.prot_p()
        with open(tmp, "rb") as fh:
            ftp.storbinary("STOR lightning.json.tmp", fh)
        try:
            ftp.delete("lightning.json")
        except ftplib.error_perm:
            pass
        ftp.rename("lightning.json.tmp", "lightning.json")
    os.unlink(tmp)
    log("✅ lightning.json uploadé : " + json.dumps(payload, ensure_ascii=False))


def main():
    strikes = asyncio.run(listen())
    payload = build_payload(strikes)
    upload(payload)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"❌ Erreur : {e}")
        sys.exit(1)
