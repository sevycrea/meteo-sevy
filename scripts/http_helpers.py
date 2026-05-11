#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Helpers HTTP robustes pour les appels aux API externes (Weather Underground,
Open-Meteo, MetNo).

PRINCIPES
- Retry avec backoff exponentiel sur erreurs réseau, timeouts et HTTP 5xx
- Retry sur 429 (rate limit) avec respect du Retry-After si présent
- PAS de retry sur 4xx (sauf 429) — une mauvaise requête ne sera jamais OK
- Timeout court (10s) pour ne pas geler un job GitHub Actions
- Log de chaque tentative pour diagnostic

USAGE
    from http_helpers import get_json_with_retry
    data = get_json_with_retry(url, params={...}, log=log)
    if data is None:
        # toutes les tentatives ont échoué, gérer le cas
        return
"""

import time
import requests


# Erreurs réseau « transitoires » qui méritent un retry
_TRANSIENT_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
    requests.exceptions.ReadTimeout,
    requests.exceptions.ConnectTimeout,
    requests.exceptions.ChunkedEncodingError,
)


def _default_log(msg):
    print(msg)


def get_json_with_retry(
    url,
    params=None,
    headers=None,
    timeout=10,
    attempts=3,
    backoff_base=2.0,
    backoff_factor=2.0,
    log=None,
):
    """Effectue un GET HTTP avec retry exponentiel, retourne le JSON décodé.

    Args:
        url           : URL à appeler
        params        : query string params (dict)
        headers       : headers HTTP (dict)
        timeout       : timeout par tentative en secondes (défaut 10s)
        attempts      : nombre total de tentatives (défaut 3 → max ~14s)
        backoff_base  : délai initial entre tentatives en secondes (défaut 2s)
        backoff_factor: facteur multiplicatif (défaut 2 → 2s, 4s, 8s...)
        log           : fonction de log (défaut: print)

    Returns:
        Le dict JSON parsé, ou None si toutes les tentatives ont échoué.

    Notes:
        - 4xx (sauf 429) → pas de retry, retourne None immédiatement
        - 5xx, 429, timeouts, erreurs réseau → retry avec backoff
        - Respecte le header Retry-After si présent sur 429
    """
    log = log or _default_log
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)

            # Cas succès : 2xx
            if 200 <= response.status_code < 300:
                try:
                    return response.json()
                except ValueError as e:
                    # JSON malformé — souvent transitoire (réponse tronquée)
                    last_error = f"JSON malformé : {e}"
                    log(f"⚠️  Tentative {attempt}/{attempts} : {last_error}")

            # Cas 4xx non-retriable (sauf 429)
            elif 400 <= response.status_code < 500 and response.status_code != 429:
                log(f"❌ HTTP {response.status_code} (non-retriable) : {response.text[:200]}")
                return None

            # Cas 429 : respecter Retry-After si présent
            elif response.status_code == 429:
                retry_after = response.headers.get('Retry-After')
                if retry_after:
                    try:
                        wait = min(float(retry_after), 60)  # cap à 60s
                        log(f"⚠️  HTTP 429 rate limit — attente {wait}s (Retry-After)")
                        time.sleep(wait)
                        continue
                    except ValueError:
                        pass
                last_error = "HTTP 429 rate limit"
                log(f"⚠️  Tentative {attempt}/{attempts} : {last_error}")

            # Cas 5xx : retriable
            else:
                last_error = f"HTTP {response.status_code}"
                log(f"⚠️  Tentative {attempt}/{attempts} : {last_error}")

        except _TRANSIENT_EXCEPTIONS as e:
            last_error = f"{type(e).__name__}: {e}"
            log(f"⚠️  Tentative {attempt}/{attempts} : {last_error}")
        except requests.exceptions.RequestException as e:
            # Erreur requests non listée — log et retry quand même
            last_error = f"{type(e).__name__}: {e}"
            log(f"⚠️  Tentative {attempt}/{attempts} (erreur inattendue) : {last_error}")

        # Backoff exponentiel avant la prochaine tentative (sauf si dernière)
        if attempt < attempts:
            delay = backoff_base * (backoff_factor ** (attempt - 1))
            time.sleep(delay)

    log(f"❌ Toutes les tentatives ont échoué ({attempts}) : {last_error}")
    return None
