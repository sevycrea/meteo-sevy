#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Upload d'un fichier log vers le serveur FTP
Usage: python scripts/upload_log_ftp.py logs/mon_fichier.log
"""

import os
import sys
from ftplib import FTP

FTP_HOST = os.environ.get("FTP_HOST", "")
FTP_USER = os.environ.get("FTP_USER", "")
FTP_PASS = os.environ.get("FTP_PASS", "")

def upload(local_path):
    if not FTP_HOST:
        print("⚠️  FTP_HOST non défini — upload ignoré")
        return

    if not os.path.exists(local_path):
        print(f"⚠️  Fichier introuvable: {local_path}")
        return

    remote_name = "logs/" + os.path.basename(local_path)

    try:
        ftp = FTP(FTP_HOST, timeout=30)
        ftp.login(FTP_USER, FTP_PASS)

        # Créer le dossier logs/ si nécessaire
        try:
            ftp.cwd("logs")
        except:
            ftp.mkd("logs")
            ftp.cwd("logs")

        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {os.path.basename(local_path)}", f)

        ftp.quit()
        print(f"✅ Log uploadé: {remote_name}")
    except Exception as e:
        print(f"❌ Erreur upload log FTP: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/upload_log_ftp.py <chemin_log>")
        sys.exit(1)
    upload(sys.argv[1])
