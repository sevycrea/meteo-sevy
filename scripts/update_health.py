#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Maintient un fichier `health.json` publié sur le serveur web/FTP qui contient
les timestamps de dernière mise à jour de chaque composant du pipeline.

USAGE
-----
À appeler en fin de chaque workflow GitHub Actions, après upload des données :

    python scripts/update_health.py --component hourly
    python scripts/update_health.py --component daily
    python scripts/update_health.py --component alerts
    python scripts/update_health.py --component predictions

Components reconnus :
    hourly       — collecte WU live (toutes les 15 min attendu)
    daily        — collecte WU history (toutes les 15 min attendu)
    alerts       — détection événements (toutes les 30 min attendu)
    predictions  — prévisions ML multihorizon + créneaux (4×/jour attendu)

CONSOMMATEURS
-------------
- App iOS / site web : lisent health.json pour détecter les "données figées".
  Si `now - last_hourly > 30 min` → bannière orange "Données possiblement obsolètes".
  Si > 2h → bannière rouge.
- UptimeRobot / cron-job.org : peut pinger health.json toutes les 5 min,
  parse le JSON et alerte si un timestamp dépasse un seuil.

FORMAT DE health.json
---------------------
{
  "generated_at": "2026-05-11T18:30:12Z",
  "overall_status": "ok",               # "ok" | "degraded" | "stale"
  "stale_components": [],                # liste des composants en retard
  "components": {
    "hourly":      { "last_run": "...", "status": "ok",       "stale": false, "age_min": 8,  "expected_interval_min": 15 },
    "daily":       { "last_run": "...", "status": "ok",       "stale": false, "age_min": 7,  "expected_interval_min": 15 },
    "alerts":      { "last_run": "...", "status": "ok",       "stale": false, "age_min": 18, "expected_interval_min": 30 },
    "predictions": { "last_run": "...", "status": "degraded", "stale": false, "age_min": 90, "expected_interval_min": 360 }
  },
  "station": "IVINEL2",
  "location": "Vinelz, Suisse"
}

Un composant est `stale: true` si son `age_min` dépasse 2× son `expected_interval_min`
(tolérance pour les délais GitHub Actions).
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftp_helpers import upload_legacy, upload_data
from io_helpers import atomic_write_json


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HEALTH_FILE = os.path.join(BASE_DIR, "data", "health.json")
LOG_FILE = os.path.join(BASE_DIR, "logs", "health.log")

EXPECTED_INTERVALS_MIN = {
    "hourly":      15,
    "daily":       15,
    "alerts":      30,
    "predictions": 360,  # 4×/jour = toutes les 6h
}

STATION = os.environ.get("WU_STATION_ID", "IVINEL2")


def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = f"[{ts}] {msg}"
    print(line)
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def load_health():
    """Charge health.json existant, retourne squelette si absent."""
    if os.path.exists(HEALTH_FILE):
        try:
            with open(HEALTH_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log(f"⚠️  health.json corrompu, réinitialisation: {e}")

    return {
        "generated_at": "",
        "components": {},
        "station": STATION,
        "location": "Vinelz, Suisse",
    }


def _compute_age_and_stale(comp_data, now):
    """Calcule l'âge en minutes et flag stale (>2× intervalle attendu)."""
    last_run_iso = comp_data.get("last_run", "")
    try:
        # Format: 2026-05-11T16:32:57Z
        last_run = datetime.strptime(last_run_iso, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
        age_min = int((now - last_run).total_seconds() / 60)
    except (ValueError, TypeError):
        age_min = None

    expected = comp_data.get("expected_interval_min", 9999)
    stale = age_min is not None and age_min > expected * 2

    comp_data["age_min"] = age_min
    comp_data["stale"] = stale
    return comp_data


def _compute_overall(health):
    """Calcule le statut global à partir des composants."""
    now = datetime.now(timezone.utc)
    stale_components = []
    has_degraded = False
    has_error = False

    for name, comp in health["components"].items():
        _compute_age_and_stale(comp, now)
        if comp.get("stale"):
            stale_components.append(name)
        if comp.get("status") == "degraded":
            has_degraded = True
        elif comp.get("status") == "error":
            has_error = True

    health["stale_components"] = stale_components
    if has_error:
        health["overall_status"] = "error"
    elif stale_components:
        health["overall_status"] = "stale"
    elif has_degraded:
        health["overall_status"] = "degraded"
    else:
        health["overall_status"] = "ok"


def update(component, status="ok", extra=None):
    """Met à jour le component dans health.json puis upload sur le FTP.

    Args:
        component : 'hourly' | 'daily' | 'alerts' | 'predictions'
        status    : 'ok' | 'degraded' | 'error'
        extra     : dict optionnel à fusionner dans le component
    """
    if component not in EXPECTED_INTERVALS_MIN:
        log(f"⚠️  Component inconnu : {component}")
        return False

    health = load_health()
    now_iso = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

    health["generated_at"] = now_iso
    comp = health["components"].get(component, {})
    comp["last_run"] = now_iso
    comp["status"] = status
    comp["expected_interval_min"] = EXPECTED_INTERVALS_MIN[component]
    if extra:
        comp.update(extra)
    health["components"][component] = comp

    # Recalcule âge, stale, overall_status pour TOUS les composants.
    # Important : ainsi un consommateur qui lit health.json voit toujours
    # un état cohérent et à jour, même si un autre composant n'a pas tourné.
    _compute_overall(health)

    # Écriture atomique via le helper centralisé
    atomic_write_json(HEALTH_FILE, health)
    log(f"✅ health.json mis à jour ({component} → {status}, overall={health['overall_status']})")
    if health.get("stale_components"):
        log(f"⚠️  Composants en retard : {health['stale_components']}")

    # Upload sur FTP (atomique grâce à ftp_helpers)
    try:
        upload_legacy(HEALTH_FILE, 'health.json', log=log)
    except Exception as e:
        log(f"⚠️  Upload legacy health.json échoué: {e}")

    upload_data(HEALTH_FILE, 'health.json', log=log)
    return True


def main():
    parser = argparse.ArgumentParser(description="Met à jour health.json")
    parser.add_argument("--component", required=True,
                        choices=list(EXPECTED_INTERVALS_MIN.keys()),
                        help="Composant qui vient de finir un cycle")
    parser.add_argument("--status", default="ok",
                        choices=["ok", "degraded", "error"],
                        help="Statut du cycle qui vient de finir")
    args = parser.parse_args()

    success = update(args.component, status=args.status)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
