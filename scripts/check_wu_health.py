#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Surveillance : (1) l'endpoint live temps réel répond-il ? (détecte clé
expirée/invalide OU url changée OU panne) ; (2) la clé WU expire-t-elle dans
<= 10 jours ? Écrit alert_body.txt et imprime ALERT/OK pour le workflow."""
import json, sys, datetime, os, urllib.request, urllib.parse

LIVE_URL = "https://sevy-creations.net/wp-admin/admin-ajax.php"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = os.path.join(ROOT, "data", "wu_key_meta.json")

alerts = []

# 1) Santé de l'endpoint live (la vraie source de vérité, résiste aux changements d'URL)
try:
    data = urllib.parse.urlencode({"action": "mws_meteo_live_get"}).encode()
    req = urllib.request.Request(LIVE_URL, data=data, method="POST")
    with urllib.request.urlopen(req, timeout=25) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    if payload.get("success") is not True:
        msg = (payload.get("data") or {}).get("message", "réponse invalide")
        alerts.append(f"🔴 Endpoint météo live EN PANNE : {msg}\n"
                      f"   → clé Wunderground invalide/expirée, ou URL/API changée.\n"
                      f"   → Régénère la clé puis lance la mise à jour (Mac ou raccourci iOS).")
except Exception as e:
    alerts.append(f"🔴 Endpoint météo live INJOIGNABLE ({e}).")

# 2) Échéance de la clé (data/wu_key_meta.json : {\"expires\": \"YYYY-MM-DD\"})
try:
    meta = json.load(open(META, encoding="utf-8"))
    exp = datetime.date.fromisoformat((meta.get("expires") or "").strip())
    days = (exp - datetime.date.today()).days
    if days <= 10:
        alerts.append(f"🟠 La clé API Wunderground expire dans {days} jour(s) (le {exp}).\n"
                      f"   → Régénère-la dès que possible et lance la mise à jour.")
except Exception:
    pass  # pas de date renseignée → on s'appuie sur la santé live ci-dessus

if alerts:
    body = ("Alerte Météo Sevy — clé Wunderground / endpoint live\n\n"
            + "\n\n".join(alerts)
            + "\n\n— Programme « Mettre à jour la clé WU » (Mac) ou raccourci iOS.")
    open(os.path.join(ROOT, "alert_body.txt"), "w", encoding="utf-8").write(body)
    print("ALERT")
else:
    print("OK")
