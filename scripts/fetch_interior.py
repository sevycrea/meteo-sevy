#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_interior.py — SNZB-02 → interior.json
Utilise aioEweLink qui gère l'authentification eWeLink en interne.
Aucune clé API à gérer, solution permanente.

Variables d'environnement :
  EWELINK_EMAIL     email du compte eWeLink
  EWELINK_PASSWORD  mot de passe eWeLink
  EWELINK_DEVICE_ID device id du SNZB-02 (défaut : a480075689)
  DATA_FTP_*        credentials FTP → ftp_helpers.py
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone

from aioEweLink import EWeLinkAPI

EMAIL     = os.environ["EWELINK_EMAIL"]
PASSWORD  = os.environ["EWELINK_PASSWORD"]
DEVICE_ID = os.environ.get("EWELINK_DEVICE_ID", "a480075689")


async def fetch_params() -> dict:
    api = EWeLinkAPI()
    things = await api.login(EMAIL, PASSWORD, "eu")

    if not things:
        raise RuntimeError("Aucun appareil retourné par eWeLink")

    print(f"   {len(things)} appareil(s) trouvé(s)")

    for thing in things:
        if thing.get("deviceid") == DEVICE_ID:
            params = thing.get("params", {})
            print(f"   Params bruts : {json.dumps(params)}")
            return params

    ids = [t.get("deviceid", "?") for t in things]
    raise RuntimeError(f"Device {DEVICE_ID!r} introuvable. Disponibles : {ids}")


def _to_temp(val) -> float | None:
    if val is None:
        return None
    v = float(val)
    if v > 100:
        v = round(v / 10.0, 1)
    return round(v, 1)


def main():
    print("→ Connexion eWeLink…")
    params = asyncio.run(fetch_params())

    temp_raw = params.get("temperature") or params.get("currentTemperature") or params.get("temp")
    humi_raw = params.get("humidity")    or params.get("currentHumidity")    or params.get("humi")
    battery  = params.get("battery")

    interior = {
        "updated":  datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "temp":     _to_temp(temp_raw),
        "humidity": int(humi_raw) if humi_raw is not None else None,
        "battery":  int(battery)  if battery  is not None else None,
        "device":   "SNZB-02",
    }
    print(f"   → {interior['temp']} °C  {interior['humidity']} %  bat {interior['battery']}")

    out_path = "/tmp/interior.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(interior, f, ensure_ascii=False)

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from ftp_helpers import upload_data
    if not upload_data(out_path, "interior.json"):
        raise RuntimeError("Upload FTP échoué")
    print("✅ interior.json uploadé")


if __name__ == "__main__":
    main()
