#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_interior.py — SNZB-02 → interior.json
Auth permanente : refresh token stocké dans GitHub Secrets.
Refresh automatique toutes les 15 min sans intervention manuelle.

Secrets GitHub requis :
  EWELINK_APP_ID       AppID depuis dev.ewelink.cc
  EWELINK_APP_SECRET   AppSecret depuis dev.ewelink.cc
  EWELINK_REFRESH_TOKEN  Refresh token obtenu via ewelink_auth_setup.py
  EWELINK_DEVICE_ID    (optionnel, défaut a480075689)
  DATA_FTP_HOST / DATA_FTP_USER / DATA_FTP_PASS
"""

import base64
import hmac
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import requests

# ── Config ────────────────────────────────────────────────────────────────────

APP_ID        = os.environ["EWELINK_APP_ID"]
APP_SECRET    = os.environ["EWELINK_APP_SECRET"]
REFRESH_TOKEN = os.environ["EWELINK_REFRESH_TOKEN"]
DEVICE_ID     = os.environ.get("EWELINK_DEVICE_ID", "a480075689")
BASE           = "https://eu-apia.coolkit.cc/v2"

# ── Auth ──────────────────────────────────────────────────────────────────────

def _sign(message: str) -> str:
    mac = hmac.new(APP_SECRET.encode(), message.encode(), hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def get_access_token() -> str:
    """
    Refresh token → access token.
    Selon la doc CoolKit : on signe la VALEUR du refresh token (pas le body JSON).
    Body : {"rt": "..."} sans grantType.
    """
    body     = json.dumps({"rt": REFRESH_TOKEN}, separators=(",", ":"))
    sign_val = _sign(REFRESH_TOKEN)          # ← signe le RT, pas le body

    r = requests.post(
        f"{BASE}/user/oauth/token",
        data=body,
        headers={
            "Content-Type":  "application/json",
            "X-CK-Appid":    APP_ID,
            "Authorization": f"Sign {sign_val}",
        },
        timeout=15,
    )
    r.raise_for_status()
    resp = r.json()
    if resp.get("error") != 0:
        raise RuntimeError(f"Refresh échoué : {resp}")
    return resp["data"]["accessToken"]

# ── Capteur ───────────────────────────────────────────────────────────────────

def get_device_params(token: str) -> dict:
    r = requests.get(
        f"{BASE}/device/thing",
        headers={"Authorization": f"Bearer {token}", "X-CK-Appid": APP_ID},
        timeout=15,
    )
    r.raise_for_status()
    resp = r.json()
    if resp.get("error") != 0:
        raise RuntimeError(f"Liste appareils : {resp}")

    for item in resp["data"].get("thingList", []):
        d = item.get("itemData", {})
        if d.get("deviceid") == DEVICE_ID:
            params = d.get("params", {})
            print(f"   Params bruts : {json.dumps(params)}")
            return params

    ids = [i.get("itemData", {}).get("deviceid") for i in resp["data"].get("thingList", [])]
    raise RuntimeError(f"Device {DEVICE_ID!r} introuvable. Disponibles : {ids}")

# ── Normalisation ─────────────────────────────────────────────────────────────

def _temp(v):
    if v is None: return None
    v = float(v)
    return round(v / 10 if v > 100 else v, 1)

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("→ Refresh token eWeLink…")
    token = get_access_token()
    print("✅ Access token obtenu")

    print("→ Lecture capteur SNZB-02…")
    params = get_device_params(token)

    interior = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temp":     _temp(params.get("temperature") or params.get("currentTemperature")),
        "humidity": int(x) if (x := params.get("humidity") or params.get("currentHumidity")) else None,
        "battery":  int(x) if (x := params.get("battery")) else None,
        "device":   "SNZB-02",
    }
    print(f"   → {interior['temp']} °C  {interior['humidity']} %  bat {interior['battery']}")

    out = "/tmp/interior.json"
    with open(out, "w") as f:
        json.dump(interior, f)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ftp_helpers import upload_data
    if not upload_data(out, "interior.json"):
        raise RuntimeError("Upload FTP échoué")
    print("✅ interior.json uploadé")


if __name__ == "__main__":
    main()
