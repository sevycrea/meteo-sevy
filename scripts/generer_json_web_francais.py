#!/usr/bin/env python3
"""
Générateur JSON pour l'interface web de la Station Météo Kap Sevy
Convertit les fichiers CSV en JSON pour affichage web
Version mise à jour pour le format français Weathercloud
"""
import os, sys, glob, json
import pandas as pd
import numpy as np
from datetime import datetime

# ── Configuration ─────────────────────────────────────────────────
BASE_DIR = "/Users/yves/Desktop/Meteo_Backups"
DATA_DIR = os.path.join(BASE_DIR, "data/csv/")
OUTPUT_JSON = os.path.join(BASE_DIR, "data/json/meteo_data.json")

# ── Chargement CSV ────────────────────────────────────────────────
def load_csv(path):
    """Charge un fichier CSV Weathercloud (format français)"""
    try:
        raw = open(path,'rb').read().decode('utf-16-le', errors='replace')
        lines = raw.splitlines()
        if not lines: 
            return None
        
        cols = lines[0].rstrip(';').split(';')
        rows = []
        for line in lines[1:]:
            parts = line.rstrip(';').split(';')
            rows.append((parts + ['']*len(cols))[:len(cols)])
        
        df = pd.DataFrame(rows, columns=cols).replace('', np.nan)
        
        # La colonne de date peut avoir différents noms
        date_col = cols[0]  # Première colonne = date
        df['date'] = pd.to_datetime(df[date_col], format='%d/%m/%Y %H:%M:%S', errors='coerce')
        
        # Convertir toutes les colonnes numériques
        for col in cols[1:]:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace(',','.', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        # Corriger la pression si nécessaire
        if 'Pression atmosphérique (hPa)' in df.columns:
            df['bar_hpa'] = df['Pression atmosphérique (hPa)'].apply(
                lambda x: x*1000 if pd.notna(x) and x < 2 else x
            )
            df.loc[df['bar_hpa'] < 900, 'bar_hpa'] = np.nan
        else:
            df['bar_hpa'] = np.nan
        
        # Filtrer les lignes avec au moins une température
        if 'Température (°C)' in df.columns:
            return df.dropna(subset=['Température (°C)'])
        else:
            return df.dropna(subset=['date'])
            
    except Exception as e:
        print(f"   ⚠️  Erreur lecture {os.path.basename(path)}: {e}")
        return None

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
    
    if not frames:
        print("❌ Aucune donnée valide trouvée")
        sys.exit(1)
    
    all_df = pd.concat(frames, ignore_index=True).sort_values('date')
    all_df['date_jour'] = all_df['date'].dt.date
    return all_df

def build_daily_json(all_df):
    """Construit les données journalières pour le JSON"""
    
    # Pluie journalière (maximum du jour)
    if 'Pluie (mm)' in all_df.columns:
        daily_rain = (all_df.groupby('date_jour')['Pluie (mm)'].max()
                      .reset_index().rename(columns={'Pluie (mm)':'pluie_mm'}))
    else:
        daily_rain = pd.DataFrame({'date_jour': all_df['date_jour'].unique(), 'pluie_mm': 0})
    
    # Agrégations
    agg_dict = {}
    
    if 'Température (°C)' in all_df.columns:
        agg_dict['temp_min'] = ('Température (°C)', 'min')
        agg_dict['temp_avg'] = ('Température (°C)', 'mean')
        agg_dict['temp_max'] = ('Température (°C)', 'max')
    
    if 'Humidité (%)' in all_df.columns:
        agg_dict['hum_avg'] = ('Humidité (%)', 'mean')
    
    if 'Vitesse moyenne du vent (km/h)' in all_df.columns:
        agg_dict['wind_avg'] = ('Vitesse moyenne du vent (km/h)', 'mean')
    
    if 'Rafale maximale de vent (km/h)' in all_df.columns:
        agg_dict['wind_max'] = ('Rafale maximale de vent (km/h)', 'max')
    
    if 'bar_hpa' in all_df.columns:
        agg_dict['pressure'] = ('bar_hpa', 'mean')
    
    daily = all_df.groupby('date_jour').agg(**agg_dict).round(1).reset_index()
    daily = daily.merge(daily_rain, on='date_jour')
    
    # Convertir en dictionnaire avec dates ISO
    daily_dict = {}
    for _, row in daily.iterrows():
        date_str = row['date_jour'].strftime('%Y-%m-%d')
        daily_dict[date_str] = {
            'temp_min': float(row.get('temp_min', 0)) if pd.notna(row.get('temp_min')) else 0,
            'temp_avg': float(row.get('temp_avg', 0)) if pd.notna(row.get('temp_avg')) else 0,
            'temp_max': float(row.get('temp_max', 0)) if pd.notna(row.get('temp_max')) else 0,
            'hum_avg': float(row.get('hum_avg', 0)) if pd.notna(row.get('hum_avg')) else 0,
            'wind_avg': float(row.get('wind_avg', 0)) if pd.notna(row.get('wind_avg')) else 0,
            'wind_max': float(row.get('wind_max', 0)) if pd.notna(row.get('wind_max')) else 0,
            'rain': float(row.get('pluie_mm', 0)) if pd.notna(row.get('pluie_mm')) else 0,
            'pressure': float(row.get('pressure', 0)) if pd.notna(row.get('pressure')) else 0,
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
        json.dump(daily_dict, f, ensure_ascii=False, indent=2, sort_keys=True)
    
    print(f"✅  Fichier JSON créé → {OUTPUT_JSON}")
    print(f"📦 Taille : {os.path.getsize(OUTPUT_JSON) / 1024:.1f} Ko")
    print("\n🌐 Prêt pour WordPress !")
    print("="*60)
