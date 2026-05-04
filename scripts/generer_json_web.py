#!/usr/bin/env python3
"""
Générateur JSON pour l'interface web de la Station Météo Kap Sevy
Convertit les fichiers CSV en JSON pour affichage web
"""
import os, sys, glob, json
import pandas as pd
import numpy as np
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────
DATA_DIR = "/Users/yves/Desktop/Meteo_Backups/Data"
OUTPUT_JSON = os.path.join(DATA_DIR, "meteo_data.json")

# ── Chargement CSV ────────────────────────────────────────────────
def load_csv(path):
    """Charge un fichier CSV Weathercloud"""
    raw = open(path,'rb').read().decode('utf-16-le', errors='replace')
    lines = raw.splitlines()
    if not lines: return None
    cols = lines[0].rstrip(';').split(';')
    rows = []
    for line in lines[1:]:
        parts = line.rstrip(';').split(';')
        rows.append((parts + ['']*len(cols))[:len(cols)])
    df = pd.DataFrame(rows, columns=cols).replace('', np.nan)
    df['date'] = pd.to_datetime(df[cols[0]], format='%d/%m/%Y %H:%M:%S', errors='coerce')
    for col in cols[1:]:
        df[col] = df[col].astype(str).str.replace(',','.', regex=False)
        df[col] = pd.to_numeric(df[col], errors='coerce')
    if 'bar (hPa)' in df.columns:
        df['bar_hpa'] = df['bar (hPa)'].apply(lambda x: x*1000 if pd.notna(x) and x < 2 else x)
        df.loc[df['bar_hpa'] < 900, 'bar_hpa'] = np.nan
    else:
        df['bar_hpa'] = np.nan
    return df.dropna(subset=['temp (°C)'])

def load_all(data_dir):
    """Charge tous les fichiers CSV Weathercloud"""
    files = sorted(glob.glob(os.path.join(data_dir, "Weathercloud*.csv")))
    if not files: 
        print(f"⚠️  Aucun CSV dans {data_dir}")
        sys.exit(1)
    print(f"✅  {len(files)} fichier(s) trouvé(s)")
    frames = []
    for f in files:
        df = load_csv(f)
        if df is not None and len(df) > 0:
            frames.append(df)
            print(f"   • {os.path.basename(f)} → {len(df)} mesures")
    all_df = pd.concat(frames, ignore_index=True).sort_values('date')
    all_df['date_jour'] = all_df['date'].dt.date
    return all_df

def build_daily_json(all_df):
    """Construit les données journalières pour le JSON"""
    daily_rain = (all_df.groupby('date_jour')['rain (mm)'].max()
                  .reset_index().rename(columns={'rain (mm)':'pluie_mm'}))
    
    daily = all_df.groupby('date_jour').agg(
        temp_min=('temp (°C)','min'),
        temp_avg=('temp (°C)','mean'),
        temp_max=('temp (°C)','max'),
        hum_avg=('hum (%)','mean'),
        wind_avg=('wspdavg (km/h)','mean'),
        wind_max=('wspdhi (km/h)','max'),
        pressure=('bar_hpa','mean'),
    ).round(1).reset_index()
    
    daily = daily.merge(daily_rain, on='date_jour')
    
    # Convertir en dictionnaire avec dates ISO
    daily_dict = {}
    for _, row in daily.iterrows():
        date_str = row['date_jour'].strftime('%Y-%m-%d')
        daily_dict[date_str] = {
            'temp_min': float(row['temp_min']) if pd.notna(row['temp_min']) else 0,
            'temp_avg': float(row['temp_avg']) if pd.notna(row['temp_avg']) else 0,
            'temp_max': float(row['temp_max']) if pd.notna(row['temp_max']) else 0,
            'hum_avg': float(row['hum_avg']) if pd.notna(row['hum_avg']) else 0,
            'wind_avg': float(row['wind_avg']) if pd.notna(row['wind_avg']) else 0,
            'wind_max': float(row['wind_max']) if pd.notna(row['wind_max']) else 0,
            'rain': float(row['pluie_mm']) if pd.notna(row['pluie_mm']) else 0,
            'pressure': float(row['pressure']) if pd.notna(row['pressure']) else 0,
        }
    
    return daily_dict

# ── MAIN ──────────────────────────────────────────────────────────
if __name__=="__main__":
    print("="*60)
    print("  Générateur JSON Météo Kap Sevy pour Web")
    print("="*60)
    
    print(f"\n📂 Dossier : {DATA_DIR}")
    if not os.path.isdir(DATA_DIR): 
        print(f"❌  Introuvable")
        sys.exit(1)
    
    print("\n🔍 Lecture des fichiers CSV...")
    all_df = load_all(DATA_DIR)
    print(f"\n📊 {len(all_df):,} mesures | {all_df['date'].min().strftime('%d/%m/%Y')} → {all_df['date'].max().strftime('%d/%m/%Y')}")
    
    print("\n🔢 Agrégation des données journalières...")
    daily_dict = build_daily_json(all_df)
    print(f"   ✓ {len(daily_dict)} jours de données")
    
    print("\n💾 Génération du fichier JSON...")
    with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
        json.dump(daily_dict, f, ensure_ascii=False, indent=2)
    
    print(f"✅  Fichier JSON créé → {OUTPUT_JSON}")
    print(f"📦 Taille : {os.path.getsize(OUTPUT_JSON) / 1024:.1f} Ko")
    print("\n🌐 Vous pouvez maintenant mettre ce fichier JSON et le HTML sur votre site web !")
    print("="*60)
