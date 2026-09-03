#!/usr/bin/env python3
"""
Analyse détaillée pour tuner les seuils d'impulsion
"""

import pandas as pd
import numpy as np

csv_path = "EURUSD_M1_202605270610_202609011829.csv"
df = pd.read_csv(csv_path, sep='\t')

print("=" * 80)
print("ANALYSE DÉTAILLÉE - TUNING SEUILS")
print("=" * 80)

# Calculer ATR
df['Range'] = df['<HIGH>'] - df['<LOW>']
df['ATR_20'] = df['Range'].rolling(window=20).mean()

# Statistiques ATR
atr_valid = df['ATR_20'].dropna()
print(f"\n📊 STATISTIQUES ATR_20")
print(f"Min:     {atr_valid.min():.5f} ({atr_valid.min()*10000:.1f} pips)")
print(f"Q1:      {atr_valid.quantile(0.25):.5f} ({atr_valid.quantile(0.25)*10000:.1f} pips)")
print(f"Median:  {atr_valid.median():.5f} ({atr_valid.median()*10000:.1f} pips)")
print(f"Q3:      {atr_valid.quantile(0.75):.5f} ({atr_valid.quantile(0.75)*10000:.1f} pips)")
print(f"Max:     {atr_valid.max():.5f} ({atr_valid.max()*10000:.1f} pips)")
print(f"Mean:    {atr_valid.mean():.5f} ({atr_valid.mean()*10000:.1f} pips)")
print(f"Stdev:   {atr_valid.std():.5f} ({atr_valid.std()*10000:.1f} pips)")

# Statistiques Range
range_valid = df['Range'].dropna()
print(f"\n📊 STATISTIQUES RANGE (HIGH-LOW)")
print(f"Min:     {range_valid.min():.5f} ({range_valid.min()*10000:.1f} pips)")
print(f"Median:  {range_valid.median():.5f} ({range_valid.median()*10000:.1f} pips)")
print(f"Mean:    {range_valid.mean():.5f} ({range_valid.mean()*10000:.1f} pips)")
print(f"Max:     {range_valid.max():.5f} ({range_valid.max()*10000:.1f} pips)")

# Amplitudes possibles (close - low)
df['Amplitude'] = df['<CLOSE>'] - df['<LOW>'].shift(20).bfill()
amp_valid = df['Amplitude'].dropna()

print(f"\n📊 STATISTIQUES AMPLITUDE (CLOSE - 20 bougies LOW)")
print(f"Min:     {amp_valid.min():.5f} ({amp_valid.min()*10000:.1f} pips)")
print(f"Median:  {amp_valid.median():.5f} ({amp_valid.median()*10000:.1f} pips)")
print(f"Mean:    {amp_valid.mean():.5f} ({amp_valid.mean()*10000:.1f} pips)")
print(f"Max:     {amp_valid.max():.5f} ({amp_valid.max()*10000:.1f} pips)")

# Recommandations de seuils
print(f"\n" + "=" * 80)
print("💡 RECOMMANDATIONS DE SEUILS")
print("=" * 80)

# Calcul seuil amplitude (recommandé: > median ATR * 2)
recom_atr_mult = 2.0
min_amp_atr = atr_valid.median() * recom_atr_mult
print(f"\n1. AMPLITUDE MINIMALE")
print(f"   Spécification: max(50 pips, 2.0 × ATR)")
print(f"   Problème: 50 pips = 0.0050 >> ATR median ({atr_valid.median()*10000:.1f} pips)")
print(f"   💥 50 pips est INVALIDE pour ces données")
print(f"")
print(f"   Recommandation RÉVISÉE:")
print(f"   - Médiane ATR: {atr_valid.median()*10000:.1f} pips")
print(f"   - 2.0 × ATR median: {min_amp_atr*10000:.1f} pips")
print(f"   - Proposé: max({atr_valid.median()*10000:.1f} pips, 2.0 × ATR)")
print(f"   - Ou plus simple: 1.5 × ATR_20 (seuil adaptatif)")

# Vérification avec seuil adaptatif
print(f"\n2. VÉRIFICATION AVEC SEUIL ADAPTATIF (1.5 × ATR_20)")

def detect_impulse_adaptive(df_sub, window=20):
    """Détecte impulsions avec seuil adaptatif"""
    if len(df_sub) < window + 1:
        return None
    
    low_idx = df_sub['<LOW>'].idxmin()
    low_price = df_sub.loc[low_idx, '<LOW>']
    close_price = df_sub.iloc[-1]['<CLOSE>']
    
    amplitude = close_price - low_price
    
    # Seuil adaptatif
    atr = df_sub['ATR_20'].iloc[-1]
    if pd.isna(atr):
        return None
    
    min_amp = max(1.5 * atr, 0.00010)  # Min 1 pip
    
    if amplitude >= min_amp:
        return {
            'amplitude': amplitude,
            'atr': atr,
            'min_amp_required': min_amp,
            'qualified': True
        }
    return None

# Scan avec seuil adaptatif
impulses_adaptive = 0
for i in range(20, min(2000, len(df)-20)):
    subset = df.iloc[i:i+20]
    impulse = detect_impulse_adaptive(subset, window=20)
    if impulse:
        impulses_adaptive += 1

print(f"   Impulsions trouvées (2000 bougies): {impulses_adaptive}")
print(f"   Densité: {impulses_adaptive/1980*100:.1f}%")

if impulses_adaptive > 0:
    print(f"   ✅ CONCLUSION: Seuil adaptatif fonctionne!")
else:
    print(f"   ⚠️  Toujours pas d'impulsions => données très plates")

# 3. Alternative: utiliser écarts de prix
print(f"\n3. ANALYSE ÉCARTS (Alternative)")
print(f"   Si amplitude est le problème, peut-être chercher les gaps (FVG)?")

df['Gap'] = (df['<LOW>'].shift(1) - df['<HIGH>'].shift(2)).abs()
gap_valid = df['Gap'].dropna()
print(f"   Gap médian: {gap_valid.median()*10000:.1f} pips")
print(f"   Gap Q75: {gap_valid.quantile(0.75)*10000:.1f} pips")
print(f"   Gap >15 pips: {(gap_valid > 0.0015).sum()} occurrences")

print(f"\n" + "=" * 80)
print("🎯 PLAN D'IMPLÉMENTATION RÉVISÉ")
print("=" * 80)
print(f"""
1. CHANGER SEUIL AMPLITUDE:
   De: max(50 pips, 2.0 × ATR)
   À:  max(1.5 × ATR_20, 10 pips) [adaptatif à volatilité réelle]
   
2. VÉRIFIER VITESSE:
   - max_candles: 20 (OK)
   
3. VÉRIFIER BOS:
   - lookback: 50 bougies (à tester)
   
4. TESTER MODÈLES:
   - Modèle A: Amplitude seule (baseline)
   - Modèle B: Amplitude + FVG (gap >15 pips)
   - Modèle C: Amplitude + FVG + Fractal
   - Modèle D: Amplitude + FVG + Fractal + Window
   
5. WALK-FORWARD:
   - 4 chunks de {len(df)//4} bougies
   - Chunk 1: {0} - {len(df)//4} (train)
   - Chunk 2: {len(df)//4} - {len(df)//2} (test)
   - Chunk 3: {len(df)//2} - {3*len(df)//4} (train)
   - Chunk 4: {3*len(df)//4} - {len(df)} (test)
""")

print("=" * 80)
