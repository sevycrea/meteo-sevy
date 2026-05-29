#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_interior.py
Récupère la température et l'humidité du capteur SONOFF SNZB-02
via l'API eWeLink v2 (région EU) et uploade interior.json sur
data.sevy-creations.net.

Variables d'environnement attendues :
  EWELINK_APP_ID       AppID depuis dev.ewelink.cc
  EWELINK_APP_SECRET   AppSecret depuis dev.ewelink.cc
  EWELINK_EMAIL        Email du compte eWeLink
  EWELINK_PASSWORD     Mot de passe du compte eWeLink
  EWELINK_DEVICE_ID    Device ID du SNZB-02 (défaut : a480075689)
  DATA_FTP_HOST / DATA_FTP_USER / DATA_FTP_PASS  → ftp_helpers.py
"""

import os
import sys
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────

APP_ID     = os.environ["EWELINK_APP_ID"]
APP_SECRET = os.environ["EWELINK_APP_SECRET"]
EMAIL      = os.environ["EWELINK_EMAIL"]
PASSWORD   = os.environ["EWELINK_PASSWORD"]
DEVICE_ID  = os.environ.get("EWELINK_DEVICE_ID", "a480075689")
BASE_URL   = "https://eu-apia.coolkit.cc/v2"

# ── Authentification ──────────────────────────────────────────────────────────

def _sign(body_str: str) -> str:
    """HMAC-SHA256(APP_SECRET, body_str) → base64."""
    mac = hmac.new(
        key=APP_SECRET.encode("utf-8"),
        msg=body_str.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


def get_token() -> str:
    """POST /v2/user/login → access_token (at).
    NB : /v2/user/oauth/token est réservé au flow OAuth2 (code navigateur).
    Pour un script serveur accédant à son propre compte, on utilise /user/login.
    """
    payload = {
        "email": EMAIL,
        "password": PASSWORD,
        "countryCode": "+41",
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    headers = {
        "Content-Type": "application/json",
        "X-CK-Appid": APP_ID,
        "Authorization": f"Sign {_sign(body_str)}",
    }
    r = requests.post(
        f"{BASE_URL}/user/login",
        data=body_str,
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    resp = r.json()
    if resp.get("error") != 0:
        raise RuntimeError(f"Auth eWeLink échouée : {resp}")
    # L'API login retourne "at" (access token), pas "accessToken"
    data = resp["data"]
    return data.get("at") or data.get("accessToken") or data["at"]

# ── Lecture du capteur ────────────────────────────────────────────────────────

def get_all_devices(token: str) -> list:
    """GET /v2/device/thing → liste de tous les appareils."""
    headers = {
        "Authorization": f"Bearer {token}",
        "X-CK-Appid": APP_ID,
    }
    r = requests.get(
        f"{BASE_URL}/device/thing",
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    resp = r.json()
    if resp.get("error") != 0:
        raise RuntimeError(f"Erreur liste appareils : {resp}")
    return resp["data"].get("thingList", [])


def find_device_params(devices: list, device_id: str) -> dict:
    """Trouve les params du capteur dans la liste."""
    for item in devices:
        data = item.get("itemData", {})
        if data.get("deviceid") == device_id:
            return data.get("params", {})
    # Afficher les IDs disponibles pour faciliter le debug
    ids = [i.get("itemData", {}).get("deviceid", "?") for i in devices]
    raise RuntimeError(
        f"Device {device_id!r} introuvable. Appareils disponibles : {ids}"
    )

# ── Normalisation des valeurs ─────────────────────────────────────────────────

def _to_temp(val) -> float | None:
    """Normalise la température (int×10 ou float direct)."""
    if val is None:
        return None
    v = float(val)
    # SNZB-02 ancien firmware : valeur en dixièmes (ex. 215 = 21.5 °C)
    if v > 100:
        v = round(v / 10.0, 1)
    return round(v, 1)


def _to_int(val) -> int | None:
    return int(val) if val is not None else None

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("→ Authentification eWeLink (EU)…")
    token = get_token()
    print("✅ Token obtenu")

    print("→ Lecture liste appareils…")
    devices = get_all_devices(token)
    print(f"   {len(devices)} appareil(s) trouvé(s)")

    params = find_device_params(devices, DEVICE_ID)
    print(f"   Params bruts : {json.dumps(params)}")

    # Clés possibles selon version firmware
    temp_raw = (
        params.get("temperature")
        or params.get("currentTemperature")
        or params.get("temp")
    )
    humi_raw = (
        params.get("humidity")
        or params.get("currentHumidity")
        or params.get("humi")
    )
    battery = params.get("battery")

    interior = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temp":     _to_temp(temp_raw),
        "humidity": _to_int(humi_raw),
        "battery":  _to_int(battery),
        "device":   "SNZB-02",
    }
    print(
        f"   → temp={interior['temp']} °C  "
        f"humi={interior['humidity']} %  "
        f"bat={interior['battery']} %"
    )

    # Écriture locale
    out_path = "/tmp/interior.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(interior, f, ensure_ascii=False)

    # Upload FTPS → data.sevy-creations.net
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ftp_helpers import upload_data  # noqa: E402

    ok = upload_data(out_path, "interior.json")
    if not ok:
        raise RuntimeError("Upload FTP vers data.sevy-creations.net échoué")
    print("✅ interior.json uploadé sur data.sevy-creations.net")


if __name__ == "__main__":
    main()
