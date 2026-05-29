#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_interior.py
Récupère la température et l'humidité du capteur SONOFF SNZB-02
via l'API v1 eWeLink (même endpoint que l'app mobile) et uploade
interior.json sur data.sevy-creations.net.

Authentification permanente : email + password à chaque run.
Aucun token à stocker, aucune expiration.

Variables d'environnement :
  EWELINK_APP_ID     AppID depuis dev.ewelink.cc
  EWELINK_APP_SECRET AppSecret depuis dev.ewelink.cc
  EWELINK_EMAIL      Email du compte eWeLink
  EWELINK_PASSWORD   Mot de passe du compte eWeLink (en clair)
  EWELINK_DEVICE_ID  Device ID du SNZB-02 (défaut : a480075689)
  DATA_FTP_*         Credentials FTP → ftp_helpers.py
"""

import os
import sys
import json
import hmac
import hashlib
import base64
import time
import random
import string
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────

APP_ID    = os.environ["EWELINK_APP_ID"]
APP_SECRET = os.environ["EWELINK_APP_SECRET"]
EMAIL     = os.environ["EWELINK_EMAIL"]
PASSWORD  = os.environ["EWELINK_PASSWORD"]
DEVICE_ID = os.environ.get("EWELINK_DEVICE_ID", "a480075689")

# API v1 (endpoint app mobile — authentification permanente email/password)
BASE_V1 = "https://eu-api.coolkit.cc:8080/api"

# ── Helpers ───────────────────────────────────────────────────────────────────

def _sign(body_str: str) -> str:
    mac = hmac.new(
        APP_SECRET.encode("utf-8"),
        body_str.encode("utf-8"),
        hashlib.sha256,
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


def _nonce(n: int = 8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))

# ── Authentification v1 ───────────────────────────────────────────────────────

def login() -> str:
    """POST /api/user/login → access token (at)."""
    payload = {
        "appid":    APP_ID,
        "email":    EMAIL,
        "password": hashlib.md5(PASSWORD.encode("utf-8")).hexdigest(),
        "ts":       int(time.time()),
        "version":  8,
        "nonce":    _nonce(),
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Sign {_sign(body_str)}",
    }
    r = requests.post(f"{BASE_V1}/user/login", data=body_str,
                      headers=headers, timeout=15)
    r.raise_for_status()
    resp = r.json()
    if resp.get("error") != 0:
        raise RuntimeError(f"Login eWeLink échoué : {resp}")
    return resp["at"]

# ── Lecture capteur ───────────────────────────────────────────────────────────

def get_devices(token: str) -> list:
    """GET /api/user/device → liste des appareils."""
    params = {
        "appid":   APP_ID,
        "ts":      int(time.time()),
        "version": 8,
        "nonce":   _nonce(),
        "lang":    "en",
    }
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(f"{BASE_V1}/user/device", params=params,
                     headers=headers, timeout=15)
    r.raise_for_status()
    resp = r.json()
    if resp.get("error") != 0:
        raise RuntimeError(f"Erreur liste appareils : {resp}")
    return resp.get("devicelist", [])


def find_params(devices: list, device_id: str) -> dict:
    """Trouve les params du SNZB-02 dans la liste."""
    for d in devices:
        if d.get("deviceid") == device_id:
            return d.get("params", {})
    ids = [d.get("deviceid", "?") for d in devices]
    raise RuntimeError(
        f"Device {device_id!r} introuvable. Disponibles : {ids}"
    )

# ── Normalisation ─────────────────────────────────────────────────────────────

def _to_temp(val) -> float | None:
    if val is None:
        return None
    v = float(val)
    if v > 100:          # dixièmes (ex. 215 = 21.5 °C)
        v = round(v / 10.0, 1)
    return round(v, 1)


def _to_int(val) -> int | None:
    return int(val) if val is not None else None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("→ Login eWeLink (API v1)…")
    token = login()
    print("✅ Token obtenu")

    print("→ Lecture appareils…")
    devices = get_devices(token)
    print(f"   {len(devices)} appareil(s)")

    params = find_params(devices, DEVICE_ID)
    print(f"   Params bruts : {json.dumps(params)}")

    temp_raw = (params.get("temperature")
                or params.get("currentTemperature")
                or params.get("temp"))
    humi_raw = (params.get("humidity")
                or params.get("currentHumidity")
                or params.get("humi"))
    battery  = params.get("battery")

    interior = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temp":     _to_temp(temp_raw),
        "humidity": _to_int(humi_raw),
        "battery":  _to_int(battery),
        "device":   "SNZB-02",
    }
    print(f"   → {interior['temp']} °C  {interior['humidity']} %  bat {interior['battery']}")

    out_path = "/tmp/interior.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(interior, f, ensure_ascii=False)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ftp_helpers import upload_data  # noqa: E402
    if not upload_data(out_path, "interior.json"):
        raise RuntimeError("Upload FTP échoué")
    print("✅ interior.json uploadé")


if __name__ == "__main__":
    main()
