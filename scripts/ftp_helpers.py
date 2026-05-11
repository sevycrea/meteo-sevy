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

UPLOAD ATOMIQUE
Tous les uploads passent par un fichier `.tmp` puis sont renommés
vers leur nom final. Cela garantit qu'aucun consommateur (site web,
app iOS) ne lit jamais un JSON tronqué : la transition d'un fichier
à l'autre est atomique côté serveur FTP.

Si l'upload casse en cours (coupure réseau, timeout), le `.tmp` reste
tronqué mais le fichier final ne bouge pas → le client lit toujours
l'ancien JSON valide.

Variables d'environnement attendues :
- Legacy   : FTP_HOST, FTP_USER, FTP_PASS
- Data sub : DATA_FTP_HOST, DATA_FTP_USER, DATA_FTP_PASS  (optionnel — si
             absentes, l'upload subdomain est sauté avec un warning)
"""

import os
from ftplib import FTP, FTP_TLS, error_perm, all_errors

# Timeout du SOCKET (s'applique à connect ET à chaque read/write pendant le
# transfert). Sans ça, un transfert bloqué peut figer un job 6h.
FTP_CONNECT_TIMEOUT = 30   # secondes pour la connexion initiale
FTP_TRANSFER_TIMEOUT = 60  # secondes pour chaque opération de transfert


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


def _atomic_store(ftp, local_path, remote_name, log):
    """Upload `local_path` vers `remote_name` de façon atomique.

    Procédure :
    1. STOR vers `remote_name.tmp`
    2. DELE `remote_name` (ignoré si n'existe pas)
    3. RNFR/RNTO de `.tmp` vers `remote_name`

    Si STOR échoue, on tente DELE du `.tmp` (best-effort) pour ne pas
    laisser de débris. Si DELE/RNFR/RNTO échoue, l'exception se propage.
    """
    tmp_name = f"{remote_name}.tmp"

    # Étape 1 : upload sur .tmp
    try:
        with open(local_path, "rb") as f:
            ftp.storbinary(f"STOR {tmp_name}", f)
    except Exception:
        # Tentative best-effort de nettoyage du .tmp tronqué
        try:
            ftp.delete(tmp_name)
        except all_errors:
            pass
        raise

    # Étape 2 : supprimer l'ancien fichier final s'il existe.
    # NB : certains serveurs FTP autorisent RNTO d'écraser directement,
    # d'autres exigent DELE d'abord. On fait DELE pour être portable.
    # On ignore l'erreur si le fichier n'existait pas (premier upload).
    try:
        ftp.delete(remote_name)
    except error_perm:
        # 550 = file not found, OK pour le premier upload
        pass
    except all_errors as e:
        log(f"⚠️  DELE {remote_name} a échoué (continuera quand même) : {e}")

    # Étape 3 : renommer .tmp vers le nom final (atomique côté serveur)
    ftp.rename(tmp_name, remote_name)


def upload_legacy(local_path, remote_name, log=print):
    """Upload un fichier sur l'ancien compte FTP (clair), atomique. Lève si échec."""
    host, user, pwd = _legacy_creds()
    if not (host and user and pwd):
        raise RuntimeError("FTP_HOST/USER/PASS manquants pour upload legacy")

    ftp = FTP(host, timeout=FTP_CONNECT_TIMEOUT)
    try:
        ftp.login(user, pwd)
        # Timeout sur les opérations de transfert (lecture/écriture socket).
        try:
            ftp.sock.settimeout(FTP_TRANSFER_TIMEOUT)
        except Exception:
            pass
        _atomic_store(ftp, local_path, remote_name, log)
        log(f"[legacy] ✅ {remote_name}")
    finally:
        try:
            ftp.quit()
        except Exception:
            pass


def upload_data(local_path, remote_name, log=print):
    """Upload sur le nouveau compte FTPS (sous-domaine data), atomique.

    Soft-fail : retourne False en cas d'erreur (le site legacy continue).
    """
    host, user, pwd = _data_creds()
    if not (host and user and pwd):
        log(f"[data] ⏭️  {remote_name} sauté (DATA_FTP_* manquants)")
        return False

    try:
        ftp = FTP_TLS(host, timeout=FTP_CONNECT_TIMEOUT)
        ftp.login(user, pwd)
        ftp.prot_p()  # canal de données chiffré
        try:
            ftp.sock.settimeout(FTP_TRANSFER_TIMEOUT)
        except Exception:
            pass
        try:
            _atomic_store(ftp, local_path, remote_name, log)
            log(f"[data]   ✅ {remote_name}")
            return True
        finally:
            try:
                ftp.quit()
            except Exception:
                pass
    except all_errors as e:
        log(f"[data]   ⚠️  upload {remote_name} échoué: {e}")
        return False
    except OSError as e:
        log(f"[data]   ⚠️  upload {remote_name} OSError: {e}")
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
