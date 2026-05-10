#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helpers FTP centralisés pour le pipeline Météo Sevy.

Deux destinations :

1. **Legacy** (ancien compte, FTP clair) — alimente
   /wp-content/themes/astra-child/data/ via le compte chrooté `ig6i34_Claude`.
   Utilisé par le site WordPress historique.

2. **Data subdomain** (nouveau compte, FTPS obligatoire) — alimente
   https://data.sevy-creations.net/ via le compte chrooté `ig6i34_data-meteo`.
   Utilisé par : nouveau site (après migration), app iOS, intégrations futures.

Phase de transition : les deux destinations sont alimentées en parallèle
(double upload). Le legacy upload reste autoritaire — un échec côté legacy
fait échouer la fonction. Un échec côté data subdomain est loggé mais ne
casse rien (l'ancien site continue de tourner).

Variables d'environnement attendues :
- Legacy   : FTP_HOST, FTP_USER, FTP_PASS
- Data sub : DATA_FTP_HOST, DATA_FTP_USER, DATA_FTP_PASS  (optionnel — si
             absentes, l'upload subdomain est sauté avec un warning)
"""

import os
from ftplib import FTP, FTP_TLS, error_perm


def _legacy_creds():
    return (
        os.environ.get("FTP_HOST", ""),
        os.environ.get("FTP_USER", ""),
        os.environ.get("FTP_PASS", ""),
    )


def _data_creds():
    return (
        os.environ.get("DATA_FTP_HOST", ""),
        os.environ.get("DATA_FTP_USER", ""),
        os.environ.get("DATA_FTP_PASS", ""),
    )


def upload_legacy(local_path, remote_name, log=print):
    """Upload un fichier sur l'ancien compte FTP (clair). Lève si échec."""
    host, user, pwd = _legacy_creds()
    if not (host and user and pwd):
        raise RuntimeError("FTP_HOST/USER/PASS manquants pour upload legacy")

    ftp = FTP(host, timeout=30)
    try:
        ftp.login(user, pwd)
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {remote_name}", f)
        log(f"[legacy] ✅ {remote_name}")
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def upload_data(local_path, remote_name, log=print):
    """Upload sur le nouveau compte FTPS (sous-domaine data). Soft-fail."""
    host, user, pwd = _data_creds()
    if not (host and user and pwd):
        log(f"[data] ⏭️  {remote_name} sauté (DATA_FTP_* manquants)")
        return False

    try:
        ftp = FTP_TLS(host, timeout=30)
        ftp.login(user, pwd)
        ftp.prot_p()  # canal de données chiffré
        try:
            with open(local_path, "rb") as f:
                ftp.storbinary(f"STOR {remote_name}", f)
            log(f"[data]   ✅ {remote_name}")
            return True
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    except (error_perm, OSError) as e:
        log(f"[data]   ⚠️  upload {remote_name} échoué: {e}")
        return False


def upload_dual(local_path, remote_name, log=print):
    """
    Upload sur les deux destinations.

    - Legacy : autoritaire (lève en cas d'échec → le site casserait sinon)
    - Data subdomain : best-effort (loggue + retourne False mais ne lève pas)

    Retourne True si data subdomain a réussi aussi, False si seulement legacy.
    """
    upload_legacy(local_path, remote_name, log=log)
    return upload_data(local_path, remote_name, log=log)
