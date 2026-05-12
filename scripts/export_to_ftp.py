#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Export et Upload FTP des Alertes Météo
Génère un JSON propre et l'upload automatiquement vers le serveur web
"""

import json
import os
from datetime import datetime, timedelta
from ftplib import FTP
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ftp_helpers import upload_data, upload_legacy
from io_helpers import atomic_write_json

# ============================================
# CONFIGURATION
# ============================================

# Chemins — relatifs à la racine du repo
BASE_DIR    = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALERTS_FILE = os.path.join(BASE_DIR, "data", "alerts_history.json")
EXPORT_JSON = os.path.join(BASE_DIR, "data", "alerts.json")
LOG_FILE    = os.path.join(BASE_DIR, "logs", "ftp_upload.log")

# FTP — credentials via variables d'environnement (GitHub Secrets)
FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")
FTP_DIR  = ""

os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ============================================
# FONCTIONS
# ============================================

def log(message):
    """Logger avec timestamp"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_message = f"[{timestamp}] {message}\n"
    print(log_message.strip())
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(log_message)

def load_alerts():
    """Charger les alertes depuis le fichier"""
    try:
        if os.path.exists(ALERTS_FILE):
            with open(ALERTS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    except Exception as e:
        log(f"⚠️  Erreur chargement alertes: {e}")
        return []

def generate_web_json(alerts):
    """Générer un JSON propre pour le web"""
    
    # Filtrer les alertes des dernières 48h
    now = datetime.now()
    cutoff = now - timedelta(hours=48)
    
    recent_alerts = []
    for alert in alerts:
        try:
            detected = datetime.fromisoformat(alert['detected_at'])
            if detected > cutoff:
                recent_alerts.append(alert)
        except:
            continue
    
    # Limiter à 20 alertes max
    recent_alerts = sorted(recent_alerts, key=lambda x: x['detected_at'], reverse=True)[:20]
    
    # Créer le JSON web
    web_data = {
        'generated_at': now.isoformat(),
        'location': 'Vinelz, Suisse',
        'total_alerts': len(recent_alerts),
        'alerts': recent_alerts
    }
    
    # Si aucune alerte, créer un JSON neutre
    if len(recent_alerts) == 0:
        web_data['status'] = 'normal'
        web_data['message'] = 'Aucune alerte météo en cours'
        web_data['alerts'] = []
    else:
        # Compter par sévérité
        critical = sum(1 for a in recent_alerts if a.get('severity') == 'critical')
        warning = sum(1 for a in recent_alerts if a.get('severity') == 'warning')
        
        if critical > 0:
            web_data['status'] = 'critical'
            web_data['message'] = f"{critical} alerte(s) critique(s) en cours"
        elif warning > 0:
            web_data['status'] = 'warning'
            web_data['message'] = f"{warning} avertissement(s) en cours"
        else:
            web_data['status'] = 'info'
            web_data['message'] = f"{len(recent_alerts)} info(s) météo"
    
    return web_data

def save_json(data):
    """Sauvegarder le JSON localement (atomique)."""
    try:
        atomic_write_json(EXPORT_JSON, data)
        log(f"✅ JSON généré: {EXPORT_JSON}")
        return True
    except Exception as e:
        log(f"❌ Erreur sauvegarde JSON: {e}")
        return False

def upload_to_ftp(local_file, remote_name):
    """Upload un fichier vers le serveur FTP (atomique via ftp_helpers)."""
    try:
        upload_legacy(local_file, remote_name, log=log)
        return True
    except Exception as e:
        log(f"❌ Erreur upload FTP atomique: {e}")
        return False

# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("📤 EXPORT ET UPLOAD FTP - ALERTES MÉTÉO")
    log("=" * 70)
    
    # 1. Charger les alertes
    log("📊 Chargement des alertes...")
    alerts = load_alerts()
    log(f"   {len(alerts)} alerte(s) dans l'historique")
    
    # 2. Générer le JSON web
    log("🔨 Génération du JSON web...")
    web_data = generate_web_json(alerts)
    log(f"   Status: {web_data['status']}")
    log(f"   Message: {web_data['message']}")
    log(f"   Alertes récentes: {web_data['total_alerts']}")
    
    # 3. Sauvegarder localement
    if not save_json(web_data):
        log("❌ Échec génération JSON")
        return 1

    # 4. Upload vers FTP
    log("")
    log("📤 Upload vers FTP...")

    if not FTP_HOST:
        log("⚠️  FTP_HOST non défini — upload ignoré")
        log("✅ JSON généré localement")
        return 0

    success_json = upload_to_ftp(EXPORT_JSON, 'alerts.json')

    # Double upload vers data.sevy-creations.net (best-effort, ne casse pas si KO)
    upload_data(EXPORT_JSON, 'alerts.json', log=log)

    # Résumé
    log("")
    log("=" * 70)
    if success_json:
        log("✅ EXPORT ET UPLOAD RÉUSSIS")
    else:
        log("⚠️  EXPORT RÉUSSI (upload FTP échoué)")
        log(f"📁 Fichier local: {EXPORT_JSON}")
    log("=" * 70)

    return 0 if success_json else 1

if __name__ == "__main__":
    sys.exit(main())
