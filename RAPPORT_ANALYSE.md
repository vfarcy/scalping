# Rapport d'Analyse: Compatibilité CSV ↔ Spécification

## 1. RÉSUMÉ EXÉCUTIF

| Critère | Résultat | Verdict |
|---------|----------|---------|
| **Structure OHLC** | ✅ Complète (9 colonnes) | OK |
| **Volume données** | ✅ 99,940 bougies | OK |
| **Durée** | ✅ 97 jours (27 mai - 1 sept 2026) | OK |
| **Timeframe** | ✅ 1 minute (M1) | OK |
| **Qualité prix** | ✅ Zéro anomalies | OK |
| **Fenêtre trading** | ✅ 62.8% en 8-22h UTC | OK |
| **Volatilité** | ⚠️ TRÈS FAIBLE (1.0 pip ATR médian) | ⚠️ PROBLÈME |
| **Impulsions** | ❌ Zéro détectées avec seuils orig. | ❌ PROBLÈME |

**VERDICT GLOBAL: 🟡 IMPLÉMENTATION POSSIBLE AVEC RÉVISIONS MAJEURES**

---

## 2. ANALYSE VOLATILITÉ

### Statistiques Clés

```
ATR_20 (Moyenne des ranges 20 bougies):
  - Minimum: 0.1 pips
  - Médian: 1.0 pips
  - Maximum: 9.6 pips
  
Range (HIGH - LOW) par bougie:
  - Minimum: 0.0 pips
  - Médian: 0.9 pips
  - Maximum: 54.9 pips
```

### Problème Critique

**Seuil original (50 pips) = 50 × ATR_médian**

- Spécification: `max(50 pips, 2.0 × ATR)`
- Dans ces données: 50 pips >> 99.9% des amplitudes réelles
- Résultat: **Aucune impulsion détectable**

### Solution

**Nouvelle règle d'amplitude:**
```
Amplitude >= max(1.5 × ATR_20, 10 pips)
```

Ou encore plus agressif:
```
Amplitude >= 1.0 × ATR_20 (pure seuil adaptatif)
```

---

## 3. DONNÉES DISPONIBLES POUR BACKTEST

### Structure Temporelle
- **Début:** 2026.05.27 06:10
- **Fin:** 2026.09.01 18:29
- **Durée:** 97 jours, 12 heures

### Distribution Temporelle
| Plage | Bougies | % |
|-------|---------|-----|
| **Lun-Ven, 8-22h UTC** | 62,722 | 62.8% |
| Hors fenêtre | 37,218 | 37.2% |

### Walk-Forward Split Recommandé
```
Chunk 1: [0, 24,985]         (25% - Train IS)
Chunk 2: [24,985, 49,970]    (25% - Test OOS)
Chunk 3: [49,970, 74,955]    (25% - Train IS2)
Chunk 4: [74,955, 99,940]    (25% - Test OOS2)
```

---

## 4. RÉVISIONS NÉCESSAIRES DE LA SPÉCIFICATION

### 4.1 Paramètre: Amplitude Minimale

**AVANT:**
```
Amplitude >= max(body_min_pips=50, k=2.0 × ATR_20)
```

**APRÈS (Adaptatif):**
```
Amplitude >= max(1.5 × ATR_20[t], 10 pips)

Avec plages de test:
- 1.0 × ATR_20 (agressif)
- 1.5 × ATR_20 (recommandé)
- 2.0 × ATR_20 (conservateur)
```

**Justification:** ATR_20 médian = 1.0 pip. Seuil 50 pips était calibré pour EURUSD haute volatilité, pas ces données.

### 4.2 Paramètre: Seuil FVG (Fair Value Gap)

**AVANT:** `gap >= 15 pips` (implicite)

**APRÈS:** `gap >= max(1.0 × ATR_20, 5 pips)`

**Justification:** Seulement 25 gaps > 15 pips dans 100k bougies = rare. Gap médian = 0.9 pips.

### 4.3 Paramètre: Buffer Stop Loss

**AVANT:** `Buffer = 5 pips` (fixe)

**APRÈS:** `Buffer = max(1.0 × ATR_20, 3 pips)`

**Justification:** Adaptatif à volatilité locale.

---

## 5. CHECKLIST IMPLÉMENTATION RÉVISÉE

### Phase 1: Préparation (FAIT)
- [x] Environnement mamba/conda activé
- [x] Pandas, Numpy installés
- [x] CSV validé (0 anomalies)
- [x] Seuils révisés

### Phase 2: Implémentation Backtest
- [ ] Classe Strategy implémentée
- [ ] Détection impulsion révisée (seuils adaptatifs)
- [ ] Gestion OrderBlock complète
- [ ] Calcul position sizing avec frais
- [ ] Backtest loop sans lookahead

### Phase 3: Validation Statistique
- [ ] Shuffle test (100 permutations)
- [ ] Calcul p-value
- [ ] Vérification H0 (marchéaléatoire)

### Phase 4: Walk-Forward
- [ ] Split 4 chunks
- [ ] IS backtest sur chunks 1+3
- [ ] OOS backtest sur chunks 2+4
- [ ] Comparaison IS vs OOS

### Phase 5: Rapports
- [ ] Matrice résultats (tous modèles)
- [ ] Equity curves
- [ ] Distribution P&L
- [ ] Sharpe ratio

---

## 6. PARAMÈTRES RÉVISÉS

### Impulse Detection (RÉVISÉ)

| Param | Original | Révisé | Plage Test |
|-------|----------|--------|-----------|
| `body_min_pips` | 50 | ~~50~~ | ~~[30, 50, 75]~~ |
| `atr_multiplier` | 2.0 | 1.5 | [1.0, 1.5, 2.0] |
| `atr_base_pips` | - | 10 | [5, 10, 15] |
| `max_candles` | 20 | 20 | [10, 15, 20, 30] |
| `bos_lookback` | 50 | 50 | [30, 50, 100] |

**Nouvelle formule:**
```python
min_amplitude = max(atr_multiplier × ATR_20[t], atr_base_pips / 10000)
```

### Filtres (RÉVISÉ)

| Filtre | Param | Valeur | Changement |
|--------|-------|--------|-----------|
| FVG | `fvg_min_pips` | ~~15~~ → `max(1.0×ATR_20, 5)` | Adaptatif |
| Swing | `fractal_periods` | 5 | Inchangé |
| Extrême | `extremum_lookback` | 20 | Inchangé |
| Window | `trading_hours` | (8, 22) UTC | Inchangé |
| Score | `min_stars` | 2 | Inchangé |

### Risk Management (INCHANGÉ)

```
Capital: 10,000 USD
Risk%: 1%
Spread: 1.2 pips
Commission: 1.0 pip
Slippage: 1.0 pip
Total frais: 3.2 pips
```

### Buffer & RR (RÉVISÉ)

| Param | Original | Révisé |
|-------|----------|--------|
| `buffer_pips` | 5 (fixe) | `max(1.0×ATR_20, 3)` (adaptatif) |
| `rr` | [1.5, 2, 3, 4] | Inchangé |
| `be_at_r` | 1.0 | Inchangé |

---

## 7. SIGNAUX ATTENDUS

Estimation du nombre de signaux/trades à déterminer lors du backtest.

### Hypothèse Conservatrice
```
Densité impulsion: ~1 toutes les 200 bougies
Taux revisite 1ère: ~80%
Score min_stars=2: ~60% pass
Densité trades attendue: ~0.25% des bougies

Sur 62,722 bougies (fenêtre trading seule):
Trades estimés: ~150-250 trades
```

### Si trop peu de trades
- Réduire `min_stars` de 2 à 1 (désactiver filtres)
- Réduire `atr_multiplier` de 1.5 à 1.0
- Réduire `atr_base_pips` de 10 à 5

---

## 8. DONNÉES MANQUANTES/CLARIFICATIONS

### Questions Résolues
✅ Format CSV OK (TSV avec tabs)  
✅ Plage temporelle adéquate  
✅ Qualité données (zéro anomalies)  
✅ ATR calculable  

### Points à Valider en Backtest
- ❓ Nombre de trades réel vs estimé
- ❓ Win rate (expectancy > 5 pips?)
- ❓ Stabilité IS vs OOS
- ❓ Sensibilité aux paramètres

---

## 9. PROCHAINES ÉTAPES

1. **Implémenter backtest.py** avec paramètres révisés
2. **Tester Model A** (baseline: impulsion seule)
3. **Générer rapport P&L** (trades, equity, stats)
4. **Si peu de trades**: réduire seuils progressivement
5. **Walk-forward validation** (4-chunks)
6. **Rapport final** avec recommandations

---

## 10. DONNÉES RÉSUMÉES

```python
# CSV Info
path = "EURUSD_M1_202605270610_202609011829.csv"
candles = 99,940
duration_days = 97
timeframe = "1M"
pairs = ["EURUSD"]

# Volatilité
atr_20_median_pips = 1.0
range_median_pips = 0.9
spread_mean_pips = 7.9

# Temporal
in_trading_window = 62,722 (62.8%)
weekend_closed = 37,218 (37.2%)

# Chunks (4-fold CV)
chunk_size = 24,985
chunks = [
    ("IS1", 0, 24985),
    ("OOS1", 24985, 49970),
    ("IS2", 49970, 74955),
    ("OOS2", 74955, 99940),
]
```

---

**Document généré:** 2026-09-03  
**Version:** Analyse v1.0  
**Status:** ✅ Prêt pour implémentation  

