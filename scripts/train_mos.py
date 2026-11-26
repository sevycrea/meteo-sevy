#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Entraînement nocturne de la prévision corrigée par la station (MOS).

1. Récupère les mesures quotidiennes de la station IVINEL2 (data.sevy-creations.net)
   et les archive dans le dépôt (data/archive/), horaire compris — le serveur
   ne garde que 90 jours d'horaire.
2. Complète le cache des prévisions archivées Open-Meteo (data/mos/).
3. Apprend, pour J0, J+1 et J+2, la correction des températures moyenne,
   minimale et maximale, et la probabilité de pluie (> 0,5 mm).
4. Évalue honnêtement chaque correction hors échantillon (entraînement
   progressif, jamais sur les jours testés) et ne l'active que si elle bat le
   modèle numérique brut sur ces mêmes jours.
5. Écrit data/models/mos_model.json (coefficients + mesures réelles).
"""

import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mos_common as mc  # noqa: E402
from io_helpers import atomic_write_json  # noqa: E402

LOG_FILE = os.path.join(mc.BASE_DIR, "logs", "training_mos.log")
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
os.makedirs(mc.NWP_CACHE_DIR, exist_ok=True)
os.makedirs(mc.ARCHIVE_DIR, exist_ok=True)

MIN_SAMPLES = 240          # en dessous : on garde le modèle précédent (> WF_START + 2 mois de test)
WF_START = 180             # premier jour de test (jours d'historique avant)
WF_STEP = 30               # réentraînement tous les 30 jours pendant le test
ALPHAS_TEMP = [0.3, 1.0, 3.0, 10.0, 30.0]
ALPHAS_RAIN = [1.0, 3.0, 10.0, 30.0]


def log(msg):
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# ============================================
# ARCHIVES DE LA STATION (ajout seul, jamais d'effacement)
# ============================================

def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def archive_station(daily, hourly, today):
    """Fusionne les mesures en ligne dans l'archive du dépôt (jours UTC
    complets uniquement : le jour en cours est partiel). Retourne l'archive
    quotidienne fusionnée, qui sert de base d'entraînement."""
    path = os.path.join(mc.ARCHIVE_DIR, "station_daily.json")
    arch = {d: v for d, v in _load_json(path, {}).items() if d < mc.iso(today)}
    before = len(arch)
    for d, v in (daily or {}).items():
        if isinstance(v, dict) and d < mc.iso(today):
            arch[d] = v
    if daily:
        atomic_write_json(path, dict(sorted(arch.items())), indent=1)
        log(f"🗄️  Archive quotidienne : {len(arch)} jours (+{len(arch) - before})")

    if not hourly:
        log("⚠️  Horaire station indisponible — archive horaire inchangée")
        return arch
    by_year = {}
    for d, v in hourly.items():
        if d < mc.iso(today):
            by_year.setdefault(d[:4], {})[d] = v
    for year, days in by_year.items():
        p = os.path.join(mc.ARCHIVE_DIR, f"station_hourly_{year}.json")
        arch_h = _load_json(p, {})
        added = 0
        for d, v in days.items():
            old = arch_h.get(d)
            n_new = len((v or {}).get("hourly", {}) or {})
            n_old = len((old or {}).get("hourly", {}) or {})
            if old is None or n_new >= n_old:
                if old is None:
                    added += 1
                arch_h[d] = v
        atomic_write_json(p, dict(sorted(arch_h.items())), indent=None)
        log(f"🗄️  Archive horaire {year} : {len(arch_h)} jours (+{added})")
    return arch


# ============================================
# JEU DE DONNÉES
# ============================================

def build_dataset(station, caches, k):
    lead = str(mc.NWP_LEAD[k])
    prim_lead1 = caches[mc.PRIMARY]["1"]
    rows = []
    for ds in sorted(station):
        target = mc.parse_date(ds)
        day = station[ds]
        ys = [day.get(v) for v in mc.TEMP_TARGETS.values()]
        rain = day.get("rain")
        if any(not isinstance(y, (int, float)) for y in ys) or not isinstance(rain, (int, float)):
            continue
        nwp = {m: caches[m][lead].get(ds) for m in mc.MODELS}
        f = mc.build_features(nwp, station, prim_lead1, target, k)
        if f is None:
            continue
        raw = [nwp[mc.PRIMARY]["tmax"], nwp[mc.PRIMARY]["tmin"]]  # même ordre que TEMP_TARGETS
        rows.append((ds, f, ys, raw, 1 if rain > mc.RAIN_THRESHOLD_MM else 0,
                     nwp[mc.PRIMARY].get("precip") or 0.0))
    if not rows:
        return None
    return {
        "dates": [r[0] for r in rows],
        "X": np.array([r[1] for r in rows], dtype=float),
        "Y": np.array([r[2] for r in rows], dtype=float),
        "RAW": np.array([r[3] for r in rows], dtype=float),
        "RAIN": np.array([r[4] for r in rows], dtype=float),
        "RAW_P": np.array([r[5] for r in rows], dtype=float),
    }


def walk_forward(n):
    if n <= WF_START:
        raise ValueError(f"{n} jours : il en faut plus de {WF_START} pour évaluer")
    for i in range(WF_START, n, WF_STEP):
        yield slice(0, i), slice(i, min(i + WF_STEP, n))


def evaluate_temp(X, y, raw, alpha):
    errs, raw_errs = [], []
    for tr, te in walk_forward(len(y)):
        m = mc.fit_ridge(X[tr], y[tr], alpha)
        pred = np.clip(mc.predict_linear(m, X[te]), raw[te] - mc.MAX_CORRECTION, raw[te] + mc.MAX_CORRECTION)
        errs.append(pred - y[te])
        raw_errs.append(raw[te] - y[te])
    return np.concatenate(errs), np.concatenate(raw_errs)


def evaluate_rain(X, y, alpha):
    probs = []
    for tr, te in walk_forward(len(y)):
        if y[tr].min() == y[tr].max():
            probs.append(np.full(te.stop - te.start, y[tr].mean()))
            continue
        m = mc.fit_logistic(X[tr], y[tr], alpha)
        probs.append(mc.predict_proba(m, X[te]))
    return np.concatenate(probs)


def train_horizon(ds, k):
    X, Y, RAW = ds["X"], ds["Y"], ds["RAW"]
    n = len(X)
    out = {"n_days": n, "first_day": ds["dates"][0], "last_day": ds["dates"][-1], "temp": {}, "metrics": {}}
    for j, name in enumerate(mc.TEMP_TARGETS):
        y, raw = Y[:, j], RAW[:, j]
        best = None
        for a in ALPHAS_TEMP:
            e, re = evaluate_temp(X, y, raw, a)
            mae = float(np.mean(np.abs(e)))
            if best is None or mae < best[0]:
                best = (mae, a, e, re)
        mae, alpha, e, re = best
        raw_mae = float(np.mean(np.abs(re)))
        use = mae < raw_mae
        model = mc.fit_ridge(X, y, alpha)
        model["use"] = bool(use)
        out["temp"][name] = model
        out["metrics"][name] = {
            "mae_corrected": round(mae, 3),
            "mae_raw_primary": round(raw_mae, 3),
            "bias_corrected": round(float(np.mean(e)), 3),
            "bias_raw_primary": round(float(np.mean(re)), 3),
            "within_2c_corrected": round(float(np.mean(np.abs(e) <= 2.0)), 3),
            "within_2c_raw_primary": round(float(np.mean(np.abs(re) <= 2.0)), 3),
            "n_test_days": int(len(e)),
            "alpha": alpha,
            "active": bool(use),
        }
        log(f"   J+{k} {name}: corrigé {mae:.2f} °C | brut {raw_mae:.2f} °C | "
            f"{'ACTIVÉ' if use else 'non activé (brut meilleur)'} (alpha {alpha})")

    # Pluie
    yr = ds["RAIN"]
    n_test = n - WF_START
    test = slice(WF_START, n)
    base = float(yr[:WF_START].mean()) if WF_START < n else float(yr.mean())
    brier_clim = float(np.mean((base - yr[test]) ** 2)) if n_test > 0 else None
    acc_raw = float(np.mean((ds["RAW_P"][test] >= mc.RAIN_THRESHOLD_MM) == yr[test])) if n_test > 0 else None
    best = None
    for a in ALPHAS_RAIN:
        p = evaluate_rain(X, yr, a)
        b = float(np.mean((p - yr[test]) ** 2))
        if best is None or b < best[0]:
            best = (b, a, p)
    brier, alpha, p = best
    acc = float(np.mean((p >= 0.5) == yr[test]))
    use = brier < brier_clim and acc >= acc_raw
    rain_model = mc.fit_logistic(X, yr, alpha)
    rain_model["use"] = bool(use)
    out["rain"] = rain_model
    out["metrics"]["rain"] = {
        "brier": round(brier, 4), "brier_climatology": round(brier_clim, 4),
        "accuracy": round(acc, 3), "accuracy_raw_primary": round(acc_raw, 3),
        "rain_day_rate": round(float(yr.mean()), 3), "n_test_days": int(n_test),
        "alpha": alpha, "active": bool(use),
    }
    log(f"   J+{k} pluie: justesse {acc*100:.0f} % (brut {acc_raw*100:.0f} %), "
        f"Brier {brier:.3f} (climatologie {brier_clim:.3f}) → {'ACTIVÉ' if use else 'non activé'}")
    return out


# ============================================
# MAIN
# ============================================

def main():
    log("=" * 70)
    log("🧠 ENTRAÎNEMENT PRÉVISION CORRIGÉE PAR LA STATION (MOS)")
    log("=" * 70)

    today = mc.today_utc()
    online = mc.fetch_station_daily(log=log)
    if not online:
        log("⚠️  meteo_data.json en ligne indisponible — entraînement sur l'archive du dépôt seule")
    station = archive_station(online, mc.fetch_station_hourly(log=log) if online else None, today)
    station = {d: v for d, v in station.items() if isinstance(v, dict)}
    if len(station) < MIN_SAMPLES:
        log(f"❌ Trop peu de jours station ({len(station)}) — modèle précédent conservé")
        sys.exit(1)
    dates = sorted(station)
    log(f"📅 Station : {len(dates)} jours complets ({dates[0]} → {dates[-1]})")

    first = mc.parse_date(dates[0]) - timedelta(days=3)
    yesterday = today - timedelta(days=1)
    caches = {}
    for m in mc.MODELS:
        caches[m] = mc.update_cache(m, first, yesterday, log=log)
        atomic_write_json(mc.cache_path(m), caches[m], indent=None)
    if not caches[mc.PRIMARY]["0"]:
        log("❌ Archive du modèle principal vide — modèle précédent conservé")
        sys.exit(1)

    result = {
        "type": "mos_station_correction",
        "trained_at": datetime.now(mc.TZ).isoformat(timespec="seconds"),
        "station": "IVINEL2",
        "primary_model": mc.PRIMARY,
        "models": mc.MODELS,
        "feature_names": mc.FEATURE_NAMES,
        "max_correction": mc.MAX_CORRECTION,
        "evaluation": f"hors échantillon, entraînement progressif (test à partir du jour {WF_START}, "
                      f"réentraînement tous les {WF_STEP} jours)",
        "horizons": {},
    }
    for k in mc.HORIZONS:
        log(f"\n📊 Échéance J+{k}")
        ds = build_dataset(station, caches, k)
        if ds is None or len(ds["X"]) < MIN_SAMPLES:
            log(f"❌ J+{k} : échantillons insuffisants ({0 if ds is None else len(ds['X'])}) — modèle précédent conservé")
            sys.exit(1)
        result["horizons"][str(k)] = train_horizon(ds, k)

    atomic_write_json(mc.MODEL_FILE, result)
    log(f"\n✅ Modèle enregistré : {mc.MODEL_FILE}")


if __name__ == "__main__":
    main()
