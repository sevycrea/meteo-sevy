#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ewelink_auth_setup.py
─────────────────────
Script à lancer UNE SEULE FOIS en local pour obtenir le refresh token
eWeLink via le flow OAuth2 officiel.

Usage :
    EWELINK_APP_ID=xxx EWELINK_APP_SECRET=yyy python scripts/ewelink_auth_setup.py

Étapes :
1. Ce script génère et affiche une URL d'autorisation.
2. Tu l'ouvres dans ton navigateur → tu te connectes à eWeLink → autorise.
3. Tu es redirigé vers https://sevy-creations.net/?code=XXXX
4. Tu copies le code depuis l'URL et tu le colles ici.
5. Le script échange le code contre les tokens et affiche le refreshToken.
6. Tu ajoutes EWELINK_REFRESH_TOKEN dans les secrets GitHub.
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
import urllib.parse

import requests

APP_ID     = os.environ.get("EWELINK_APP_ID")     or input("AppID     : ").strip()
APP_SECRET = os.environ.get("EWELINK_APP_SECRET") or input("AppSecret : ").strip()
REDIRECT   = "https://sevy-creations.net/"
BASE_URL   = "https://eu-apia.coolkit.cc/v2"


def _sign(message: str) -> str:
    mac = hmac.new(
        key=APP_SECRET.encode("utf-8"),
        msg=message.encode("utf-8"),
        digestmod=hashlib.sha256,
    )
    return base64.b64encode(mac.digest()).decode("utf-8")


def _nonce(n=8) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


def build_oauth_url() -> str:
    seq   = str(int(time.time() * 1000))   # ms
    nonce = _nonce()
    # Message signé = APP_ID + "_" + seq
    sign  = _sign(f"{APP_ID}_{seq}")
    params = {
        "clientId":     APP_ID,
        "seq":          seq,
        "authorization": sign,
        "redirectUrl":  REDIRECT,
        "nonce":        nonce,
        "grantType":    "authorization_code",
        "state":        nonce,
    }
    return "https://c2ccdn.coolkit.cc/oauth/index.html?" + urllib.parse.urlencode(params)


def exchange_code(code: str) -> dict:
    # Décoder le code si l'URL a été copiée avec encodage %XX
    code = urllib.parse.unquote(code).strip()
    print(f"   Code utilisé  : {code!r}")
    print(f"   redirectUrl   : {REDIRECT!r}")

    payload = {
        "code":        code,
        "redirectUrl": REDIRECT,
        "grantType":   "authorization_code",
    }
    body_str = json.dumps(payload, separators=(",", ":"))
    sign_val = _sign(body_str)
    print(f"   Body envoyé   : {body_str}")
    print(f"   Sign          : {sign_val}")

    headers = {
        "Content-Type": "application/json",
        "X-CK-Appid":   APP_ID,
        "Authorization": f"Sign {sign_val}",
    }
    r = requests.post(f"{BASE_URL}/user/oauth/token", data=body_str, headers=headers, timeout=15)
    print(f"   HTTP status   : {r.status_code}")
    r.raise_for_status()
    return r.json()


def main():
    url = build_oauth_url()
    print("\n" + "═" * 60)
    print("ÉTAPE 1 — Ouvre cette URL dans ton navigateur :")
    print()
    print(url)
    print()
    print("ÉTAPE 2 — Connecte-toi avec ton compte eWeLink et autorise.")
    print("ÉTAPE 3 — Tu seras redirigé vers :")
    print(f"  {REDIRECT}?code=XXXX...")
    print("           ↑ copie la valeur de 'code' dans l'URL")
    print("═" * 60 + "\n")

    raw = input("Colle l'URL complète de redirection (ou juste le code) : ").strip()
    if not raw:
        print("Rien saisi. Abandon.")
        sys.exit(1)
    # Extraire automatiquement le code si l'URL entière a été collée
    if raw.startswith("http"):
        parsed = urllib.parse.urlparse(raw)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        if not code:
            print(f"Impossible de trouver 'code=' dans l'URL : {raw}")
            sys.exit(1)
        print(f"   Code extrait  : {code}")
    else:
        code = raw

    print("\n→ Échange du code contre les tokens…")
    resp = exchange_code(code)
    print(f"   Réponse brute : {json.dumps(resp)}")

    if resp.get("error") != 0:
        print(f"\n❌ Erreur : {resp}")
        sys.exit(1)

    data = resp["data"]
    # eWeLink peut retourner "accessToken" ou "at" selon la version
    at = data.get("accessToken") or data.get("at")
    rt = data.get("refreshToken") or data.get("rt")
    at_exp = data.get("atExpiredTime", "?")
    rt_exp = data.get("rtExpiredTime", "?")

    print("\n" + "═" * 60)
    print(f"   Réponse data complète : {json.dumps(data)}")
    print()

    if not at:
        print("❌ accessToken introuvable dans la réponse !")
        print(f"   Clés disponibles : {list(data.keys())}")
        sys.exit(1)

    print(f"✅ accessToken  ({len(at)} chars) : {at[:8]}…{at[-4:]}")
    print(f"✅ refreshToken ({len(rt) if rt else 0} chars) : {(rt[:8] + '…' + rt[-4:]) if rt else 'absent'}")
    print(f"   AT expire : {at_exp}  |  RT expire : {rt_exp}")
    print("═" * 60)

    # Mise à jour automatique du secret GitHub via gh CLI
    import subprocess
    repo = "sevycrea/meteo-sevy"
    print(f"\n→ Mise à jour du secret EWELINK_ACCESS_TOKEN sur {repo}…")
    try:
        result = subprocess.run(
            ["gh", "secret", "set", "EWELINK_ACCESS_TOKEN",
             "--repo", repo, "--body", at],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            print("✅ Secret EWELINK_ACCESS_TOKEN mis à jour automatiquement !")
        else:
            raise RuntimeError(result.stderr)
    except FileNotFoundError:
        print("⚠️  gh CLI non trouvé — copie manuellement :")
        print(f"   gh secret set EWELINK_ACCESS_TOKEN --repo {repo} --body '{at}'")
    except Exception as e:
        print(f"⚠️  Erreur gh : {e}")
        print(f"   Commande manuelle :")
        print(f"   gh secret set EWELINK_ACCESS_TOKEN --repo {repo} --body '{at}'")

    print("\n✅ Terminé — relance le workflow GitHub Actions.\n")


if __name__ == "__main__":
    main()
