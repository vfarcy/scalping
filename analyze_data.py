#!/usr/bin/env python3
"""
Analyse du CSV EURUSD M1 pour compatibilité avec la spécification
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os

# Chemin du CSV
csv_path = "EURUSD_M1_202605270610_202609011829.csv"

print("=" * 80)
print("ANALYSE DATA EURUSD M1 - Vérification Compatibilité Spécification")
print("=" * 80)

# 1. Charger les données
try:
    df = pd.read_csv(csv_path, sep='\t')
    print(f"\n✅ CSV chargé avec succès")
except Exception as e:
    print(f"\n❌ Erreur chargement CSV: {e}")
    exit(1)

# 2. Afficher structure
print(f"\n📊 STRUCTURE DES DONNÉES")
print(f"-" * 80)
print(f"Colonnes: {list(df.columns)}")
print(f"Nombre de bougies: {len(df)}")
print(f"Dtype: {df.dtypes.to_dict()}")

# 3. Valider colonnes requises
required_cols = ['<DATE>', '<TIME>', '<OPEN>', '<HIGH>', '<LOW>', '<CLOSE>']
missing = [c for c in required_cols if c not in df.columns]
if missing:
    print(f"\n❌ COLONNES MANQUANTES: {missing}")
    exit(1)
else:
    print(f"\n✅ Toutes les colonnes requises présentes")

# 4. Infos temporelles
print(f"\n⏱️  PLAGE TEMPORELLE")
print(f"-" * 80)
first_date = df['<DATE>'].iloc[0]
first_time = df['<TIME>'].iloc[0]
last_date = df['<DATE>'].iloc[-1]
last_time = df['<TIME>'].iloc[-1]

print(f"Début: {first_date} {first_time}")
print(f"Fin:   {last_date} {last_time}")

# Vérifier format date
try:
    first_dt = pd.to_datetime(f"{first_date} {first_time}", format="%Y.%m.%d %H:%M:%S")
    last_dt = pd.to_datetime(f"{last_date} {last_time}", format="%Y.%m.%d %H:%M:%S")
    duration = last_dt - first_dt
    print(f"Durée totale: {duration.days} jours, {duration.seconds // 3600} heures")
except Exception as e:
    print(f"⚠️  Erreur parse datetime: {e}")

# 5. Vérifier intégrité des prix
print(f"\n💱 QUALITÉ DES PRIX")
print(f"-" * 80)
print(f"OPEN    - min: {df['<OPEN>'].min():.5f}, max: {df['<OPEN>'].max():.5f}, mean: {df['<OPEN>'].mean():.5f}")
print(f"HIGH    - min: {df['<HIGH>'].min():.5f}, max: {df['<HIGH>'].max():.5f}")
print(f"LOW     - min: {df['<LOW>'].min():.5f}, max: {df['<LOW>'].max():.5f}")
print(f"CLOSE   - min: {df['<CLOSE>'].min():.5f}, max: {df['<CLOSE>'].max():.5f}, mean: {df['<CLOSE>'].mean():.5f}")

# Vérifier cohérence HIGH/LOW/OPEN/CLOSE
errors = 0
for i, row in df.iterrows():
    o, h, l, c = row['<OPEN>'], row['<HIGH>'], row['<LOW>'], row['<CLOSE>']
    if not (h >= max(o, c) and l <= min(o, c)):
        errors += 1

print(f"\nAnomalies HIGH/LOW: {errors} / {len(df)}")
if errors == 0:
    print(f"✅ Cohérence prix OK")
else:
    print(f"⚠️  {errors} bougies incohérentes")

# 6. Volume et volatilité
print(f"\n📈 VOLATILITÉ & VOLUME")
print(f"-" * 80)
print(f"TICKVOL - min: {df['<TICKVOL>'].min()}, max: {df['<TICKVOL>'].max()}, mean: {df['<TICKVOL>'].mean():.1f}")
print(f"SPREAD  - min: {df['<SPREAD>'].min()}, max: {df['<SPREAD>'].max()}, mean: {df['<SPREAD>'].mean():.1f}")

# Calculer ATR 20 (exemple première bougie disponible)
df['Range'] = df['<HIGH>'] - df['<LOW>']
df['ATR_20'] = df['Range'].rolling(window=20).mean()

print(f"\nATR_20 (moyenne des ranges 20 bougies)")
print(f"  - min: {df['ATR_20'].dropna().min():.5f}")
print(f"  - max: {df['ATR_20'].dropna().max():.5f}")
print(f"  - mean: {df['ATR_20'].dropna().mean():.5f}")

# 7. Détection impulsions (quick check)
print(f"\n🚀 DÉTECTION IMPULSIONS (QUICK CHECK)")
print(f"-" * 80)

def detect_impulse_quick(df, start_idx, window=20):
    """Détecte impulsions simplement"""
    if start_idx + window >= len(df):
        return None
    
    subset = df.iloc[start_idx:start_idx+window]
    low_idx = subset['<LOW>'].idxmin()
    low_price = df.loc[low_idx, '<LOW>']
    close_price = df.iloc[start_idx+window]['<CLOSE>']
    
    amplitude = close_price - low_price
    atr = df.loc[start_idx+window, 'ATR_20']
    
    if atr is np.nan:
        return None
    
    min_amp = max(0.0050, 2.0 * atr)
    
    if amplitude >= min_amp:
        return {
            'start_idx': start_idx,
            'low_idx': low_idx,
            'amplitude': amplitude,
            'atr': atr,
            'qualified': True
        }
    return None

# Scan les 500 premières bougies
impulses_found = 0
for i in range(20, min(500, len(df)-20)):
    impulse = detect_impulse_quick(df, i, window=20)
    if impulse:
        impulses_found += 1

print(f"Impulsions détectées (scan 500 premières bougies): {impulses_found}")
print(f"Densité: {impulses_found/480*100:.1f}% des bougies")

if impulses_found == 0:
    print(f"⚠️  ATTENTION: Pas d'impulsions détectées => données trop plates?")
else:
    print(f"✅ Impulsions trouvées => données exploitables")

# 8. Vérifier fenêtre de trading UTC
print(f"\n🕐 FENÊTRE DE TRADING (UTC 8-22h)")
print(f"-" * 80)

df['DateTime'] = pd.to_datetime(df['<DATE>'] + ' ' + df['<TIME>'], format="%Y.%m.%d %H:%M:%S")
df['Hour'] = df['DateTime'].dt.hour
df['DayOfWeek'] = df['DateTime'].dt.dayofweek

in_window = df[(df['Hour'] >= 8) & (df['Hour'] <= 22) & (df['DayOfWeek'] < 5)]
outside_window = len(df) - len(in_window)

print(f"Bougies en fenêtre (lun-ven, 8-22h UTC): {len(in_window)} / {len(df)} ({len(in_window)/len(df)*100:.1f}%)")
print(f"Bougies hors fenêtre: {outside_window} ({outside_window/len(df)*100:.1f}%)")

if len(in_window) < len(df) * 0.3:
    print(f"⚠️  Données peu concentrées en trading hours")
else:
    print(f"✅ Assez de données en fenêtre de trading")

# 9. Résumé
print(f"\n" + "=" * 80)
print(f"RÉSUMÉ COMPATIBILITÉ SPÉCIFICATION")
print(f"=" * 80)

checks = {
    "Colonnes OHLC": len(missing) == 0,
    "Bougies suffisantes (>1000)": len(df) > 1000,
    "Plage temporelle adéquate": duration.days > 90,
    "Cohérence prix": errors == 0,
    "ATR calculable (20+)": len(df) >= 20,
    "Impulsions détectables": impulses_found > 10,
    "Fenêtre trading OK": len(in_window) > len(df) * 0.2,
}

print()
for check, result in checks.items():
    status = "✅" if result else "❌"
    print(f"{status} {check}")

# Score global
score = sum(checks.values()) / len(checks) * 100
print(f"\n📊 SCORE COMPATIBILITÉ: {score:.0f}%")

if score >= 75:
    print(f"🟢 VERDICT: IMPLÉMENTATION POSSIBLE")
elif score >= 50:
    print(f"🟡 VERDICT: IMPLÉMENTATION POSSIBLE AVEC RÉSERVES")
else:
    print(f"🔴 VERDICT: IMPLÉMENTATION DIFFICILE")

# 10. Recommandations
print(f"\n💡 RECOMMANDATIONS")
print(f"-" * 80)
if len(df) < 10000:
    print(f"- Dataset relativement petit ({len(df)} bougies), résultats OOS peu fiables")
if impulses_found < 50:
    print(f"- Peu d'impulsions trouvées => tuner seuils amplitude/vitesse")
if outside_window / len(df) > 0.5:
    print(f"- Beaucoup de données hors trading hours => filtrage strict requis")

print("\n" + "=" * 80)
