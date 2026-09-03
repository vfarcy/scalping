# AMENDEMENT SPÉCIFICATION v2.1 - Adaptation EURUSD M1 2026

## 0. CONTEXTE

**Issue:** Spécification v2.0 calibrée pour EURUSD haute volatilité (50+ pips ATR).
**Données réelles:** EURUSD 2026 M1 très plate (1.0 pips ATR médian).
**Solution:** Adapter seuils de manière **data-driven** (adaptatif).

---

## A. CHANGEMENTS CRITIQUES

### A1. Amplitude Minimale (RÉVISION MAJEURE)

**Section 2.1, Cas Haussier, Condition 1:**

❌ **AVANT:**
```
Amplitude ≥ max(body_min_pips=50, k × ATR_20)
```

✅ **APRÈS:**
```
Amplitude ≥ max(k × ATR_20[t], min_amp_pips)

Où:
  k = [1.0, 1.5, 2.0]  (plages de test)
  min_amp_pips = [5, 10, 15] pips (adaptés à volatilité)
  
Recommandé pour données 2026: k=1.5, min_amp_pips=10
```

**Justification:**
- ATR_20 médian = 1.0 pip
- Seuil 50 pips > 99% des données
- Nouveau seuil = 15-20 pips (adaptatif)

---

### A2. Seuil Fair Value Gap (RÉVISION MAJEURE)

**Section 5, Filtre 1:**

❌ **AVANT:**
```
Gap ≥ fvg_min_pips = 15 pips (fixe)
```

✅ **APRÈS:**
```
Gap ≥ max(fvg_multiplier × ATR_20[t], fvg_min_pips)

Où:
  fvg_multiplier = [0.5, 1.0, 2.0] (plages de test)
  fvg_min_pips = [3, 5, 10] pips
  
Recommandé: multiplier=1.0, min_pips=5
```

**Justification:**
- Gap médian = 0.9 pips
- Seuil 15 pips = seulement 25 occurrences en 100k bougies
- Nouveau seuil = 1-5 pips (fréquence meilleure)

---

### A3. Buffer Stop Loss (RÉVISION MINEURE)

**Section 6, Stop Loss:**

❌ **AVANT:**
```
SL = Z_low - Buffer
Buffer = 5 pips (fixe)
```

✅ **APRÈS:**
```
SL = Z_low - max(buffer_multiplier × ATR_20[t], buffer_min_pips)

Où:
  buffer_multiplier = [0.5, 1.0, 2.0]
  buffer_min_pips = [2, 3, 5]
  
Recommandé: multiplier=1.0, min_pips=3
```

**Justification:**
- Volatilité locale doit dicter la distance SL
- 5 pips fixes = 5× ATR médian (beaucoup trop)
- Nouveau seuil = 1-5 pips (proportionnel)

---

## B. PARAMÈTRES TABLE RÉVISÉE

### B1. Impulse Detection

| Param | Valeur | Ancien | Plage Test | Unité |
|-------|--------|--------|-----------|-------|
| `atr_multiplier` | 1.5 | 2.0 | [1.0, 1.5, 2.0] | × ATR |
| `atr_base_pips` | 10 | ~~50~~ | [5, 10, 15] | pips |
| `max_candles` | 20 | 20 | [10, 15, 20, 30] | bougies |
| `bos_lookback` | 50 | 50 | [30, 50, 100] | bougies |

**Nouvelle Formule:**
```python
min_amp = max(atr_multiplier * ATR_20[t], atr_base_pips / 10000)
amplitude_ok = (close[t] - low[t0]) >= min_amp
```

### B2. Filtres

| Filtre | Param | Valeur | Ancien | Unité |
|--------|-------|--------|--------|-------|
| FVG | `fvg_multiplier` | 1.0 | ~15 | × ATR |
| FVG | `fvg_min_pips` | 5 | ~~15~~ | pips |
| Swing | `fractal_periods` | 5 | 5 | bougies |
| Extrême | `extremum_lookback` | 20 | 20 | bougies |
| Window | `trading_hours` | (8,22) | (8,22) | UTC |
| Score | `min_stars` | 2 | 2 | - |

### B3. Risk Management (INCHANGÉ)

| Param | Valeur |
|-------|--------|
| `capital` | 10,000 USD |
| `risk_pct` | 1.0% |
| `spread_pips` | 1.2 |
| `commission_pips` | 1.0 |
| `slippage_pips` | 1.0 |
| **Total** | 3.2 pips |

### B4. Gestion Position

| Param | Valeur | Ancien | Unité |
|-------|--------|--------|-------|
| `buffer_multiplier` | 1.0 | ~~5 pips~~ | × ATR |
| `buffer_min_pips` | 3 | ~~5~~ | pips |
| `be_at_r` | 1.0 | 1.0 | × RR |
| `rr` | [1.5, 2, 3, 4] | [1.5, 2, 3, 4] | - |

---

## C. DÉTECTION IMPULSION (Pseudo-code Révisé)

```python
def detect_impulse_revised(candles, t, params):
    """Détecte impulsion avec seuils adaptatifs"""
    
    if t < params['max_candles'] + 10:
        return None, None, None
    
    # Chercher plus bas local
    window = candles[t - params['max_candles']:t+1]
    lows = [c.low for c in window]
    t0 = t - params['max_candles'] + np.argmin(lows)
    low_start = candles[t0].low
    
    # 1. AMPLITUDE ADAPTATIVE
    atr = compute_atr(candles, t, 20)
    min_amplitude = max(
        params['atr_multiplier'] * atr,
        params['atr_base_pips'] / 10000
    )
    amplitude = candles[t].close - low_start
    amplitude_ok = amplitude >= min_amplitude
    
    # 2. VITESSE (inchangé)
    speed_ok = (t - t0) <= params['max_candles']
    
    # 3. BOS (inchangé)
    bos_window = candles[max(0, t0-params['bos_lookback']):t0]
    swing_low = min([c.low for c in bos_window])
    bos_ok = (candles[t].low < swing_low < candles[t].close)
    
    # 4. Pas de continuation (inchangé)
    continuation_ok = not (
        candles[t-2].close > candles[t-2].open and
        candles[t-1].close > candles[t-1].open
    )
    
    if amplitude_ok and speed_ok and bos_ok and continuation_ok:
        return ('up', t0, np.argmin(lows[:len(lows)-params['max_candles']]))
    
    return None, None, None
```

---

## D. FILTRE 1: FVG (Révisé)

```python
def check_filter_fvg(candles, t_before_impulse, params, atr_20):
    """Filtre FVG avec seuil adaptatif"""
    
    t_after = t_before_impulse + 1
    if t_after >= len(candles):
        return False
    
    # Gap = low[t_after] - high[t_before]
    gap = candles[t_after].low - candles[t_before_impulse].high
    
    # Seuil adaptatif
    min_gap = max(
        params['fvg_multiplier'] * atr_20[t_before_impulse],
        params['fvg_min_pips'] / 10000
    )
    
    return gap >= min_gap
```

---

## E. IMPACT ATTENDU

### Avant (v2.0, seuil fixe 50 pips):
```
Impulsions détectées: 0
Trades estimés: 0
Backtest: IMPOSSIBLE
```

### Après (v2.1, seuil adaptatif 10-20 pips):
```
Impulsions détectées: ~200-500
Densité: ~0.2% - 0.5%
Trades estimés: ~100-300
Backtest: POSSIBLE
```

---

## F. MATRICE DE TESTS RÉVISÉE

### Test 1: Baseline (Impulse seule)
```
atr_multiplier = 1.5
atr_base_pips = 10
bos_lookback = 50
min_stars = 1 (impulse seule)
```

### Test 2: +FVG
```
... (baseline) +
fvg_multiplier = 1.0
fvg_min_pips = 5
min_stars = 2
```

### Test 3: +FVG +Swing
```
... (Test 2) +
fractal_periods = 5
min_stars = 3
```

### Test 4: +FVG +Swing +Extrême +Window
```
... (Test 3) +
extremum_lookback = 20
trading_hours = (8, 22)
min_stars = 4
```

---

## G. WALK-FORWARD REVISED

### Data Split
```
Dataset: 99,940 bougies (27 mai - 1 sept 2026)

Chunk 1 (IS1): [0, 24,985]         (25%) - Train
Chunk 2 (OOS1): [24,985, 49,970]   (25%) - Test
Chunk 3 (IS2): [49,970, 74,955]    (25%) - Train
Chunk 4 (OOS2): [74,955, 99,940]   (25%) - Test
```

### Acceptance Criteria (INCHANGÉ)
```
OOS Sharpe ≥ 80% × IS Sharpe
OOS Profit Factor ≥ 90% × IS Profit Factor
OOS Win Rate ≥ 70% × IS Win Rate
```

---

## H. CHECKLIST IMPLÉMENTATION

- [ ] Charger CSV et valider structure
- [ ] Implement Classe Strategy avec params adaptatifs
- [ ] Implémenter detect_impulse_revised()
- [ ] Implémenter check_filter_fvg() révisé
- [ ] Backtest boucle principale
- [ ] Calcul P&L avec frais
- [ ] Shuffle test (100 permutations)
- [ ] Rapport résultats (Modèles A-D)
- [ ] Walk-forward 4-chunks
- [ ] Visualisations (equity, P&L dist)
- [ ] Documentation finale

---

## I. MIGRATION DE CODE

Pour mettre à jour votre implémentation Python:

```python
# AVANT:
params = {
    'body_min_pips': 50,
    'atr_multiplier': 2.0,
    'fvg_min_pips': 15,
    'buffer_pips': 5,
}

# APRÈS:
params = {
    'atr_multiplier': 1.5,
    'atr_base_pips': 10,
    'fvg_multiplier': 1.0,
    'fvg_min_pips': 5,
    'buffer_multiplier': 1.0,
    'buffer_min_pips': 3,
    'max_candles': 20,
    'bos_lookback': 50,
    'min_stars': 2,
    'capital': 10000,
    'risk_pct': 0.01,
}
```

---

**Version:** 2.1  
**Date:** 2026-09-03  
**Status:** ✅ Prêt pour implémentation  
**Référence:** RAPPORT_ANALYSE.md

