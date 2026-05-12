#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helpers d'I/O fichiers atomiques pour le pipeline Météo Sevy.

Garantit qu'aucun consommateur (script du même pipeline, app iOS, site web)
ne lit jamais un fichier JSON tronqué, même si :
  - Le runner GitHub Actions est tué brutalement (timeout, kill)
  - Le processus Python crash mid-write
  - Une autre instance écrit en concurrence sur le même fichier

PRINCIPE
--------
1. Écrire le contenu dans `<path>.tmp` (fichier temporaire à côté du final)
2. `os.replace(tmp, final)` — atomique sur tous les systèmes POSIX/Linux
3. Si exception en cours d'écriture → on supprime le `.tmp` (best-effort) et
   le fichier final reste intact

Le `os.replace` est garanti atomique par le kernel : un lecteur ouvre soit
l'ancien fichier complet, soit le nouveau fichier complet, jamais un mix.
"""

import json
import os
from typing import Any


def atomic_write_json(path: str, data: Any, *, indent: int = 2,
                      ensure_ascii: bool = False, sort_keys: bool = False) -> None:
    """Écrit `data` en JSON dans `path` de façon atomique.

    Args:
        path         : chemin du fichier final
        data         : objet sérialisable en JSON
        indent       : indentation (défaut 2)
        ensure_ascii : si True, échappe les non-ASCII (défaut False = UTF-8)
        sort_keys    : si True, trie les clés (défaut False)

    Raises:
        OSError       : si l'écriture du .tmp échoue
        TypeError     : si data n'est pas sérialisable
        Exception     : toute erreur lève normalement, mais le .tmp est nettoyé.
    """
    # S'assurer que le dossier parent existe
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, ensure_ascii=ensure_ascii,
                      sort_keys=sort_keys)
            # Force le flush + fsync pour éviter une perte si le runner
            # est tué juste après le replace mais avant le sync disque.
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                # fsync peut échouer sur certains FS exotiques (tmpfs) — non bloquant
                pass
        # Le rename atomique : POSIX garantit qu'à tout instant, un lecteur
        # voit soit l'ancien contenu complet, soit le nouveau complet.
        os.replace(tmp_path, path)
    except Exception:
        # Nettoyage best-effort du .tmp (ne pas masquer l'exception originale)
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise


def atomic_write_text(path: str, content: str, encoding: str = "utf-8") -> None:
    """Variante pour écrire du texte brut (non JSON) de façon atomique."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise
