# Backtest Fibonacci OTE — Or (GC=F)

Backtest d'une stratégie de trading basée sur les zones **Fibonacci OTE (Optimal Trade Entry)** appliquée à l'or (`GC=F`), sur des données réelles en 1 minute téléchargées depuis Yahoo Finance.

## Fonctionnement

1. **Récupération des données** : téléchargement des bougies en 1 minute via `yfinance` (période de 7 jours, limite maximale imposée par Yahoo Finance pour cette unité de temps). En cas d'échec (pas de connexion internet), le script se rabat automatiquement sur un fichier CSV local (`mock_gold_data.csv`).
2. **Détection de tendance** : une EMA 200 détermine le biais haussier ou baissier.
3. **Stratégie Fibonacci OTE** :
   - Identification des swings hauts/bas récents.
   - Calcul de la zone d'entrée optimale (retracement à 62 %).
   - Stop loss sous/au-dessus du swing, take profit basé sur un ratio risque/rendement.
   - Sécurisation à Break Even après cassure de structure (BOS).
4. **Résultats** : courbe d'évolution du capital, statistiques (trades gagnants/perdants/BE, win rate, profit net) et export d'un graphique PNG.
5. **Analyse de performance** : indicateurs avancés (profit factor, gain/perte moyens, espérance par trade, drawdown maximum) accompagnés d'une interprétation textuelle automatique de la robustesse de la stratégie.
6. **Journal d'exécution** : à chaque run, un fichier `journal_execution_<horodatage>.log` est généré, détaillant le téléchargement des données, l'analyse structurelle/technique (EMA 200, swings, zone OTE) et l'exécution/protection de chaque trade (entrée, SL, TP, déclenchement du BE, résultat).
7. **Analyse par tranche horaire** : comparaison automatique de la performance (win rate, profit factor, espérance) des trades ouverts durant la session de volatilité américaine (14h30-17h00, heure de l'horodatage des données) par rapport au reste de la journée.

## Prérequis

```bash
pip install pandas numpy matplotlib yfinance
```

## Utilisation

```bash
python backtest_real_data.py
```

Le script :
- télécharge les 7 derniers jours de données en 1 minute pour `GC=F`,
- exécute le backtest,
- affiche les statistiques dans la console,
- enregistre le graphique de performance sous `backtest_real_performance.png` (dans le même dossier que le script),
- affiche une analyse de performance détaillée (profit factor, drawdown maximum, espérance par trade) suivie d'une interprétation qualitative de la stratégie,
- compare la performance de la session de volatilité américaine (14h30-17h00) au reste de la journée,
- génère un journal d'exécution horodaté (`journal_execution_<AAAAMMJJ_HHMMSS>.log`) reprenant les 4 étapes clés (téléchargement, analyse technique, exécution/protection, analyse par tranche horaire) ainsi que le détail de chaque trade.

### Personnaliser la fenêtre horaire analysée

La fonction `analyze_session_performance(trades, session_start=(14, 30), session_end=(17, 0))` accepte des bornes personnalisées (heure, minute) si vous souhaitez comparer une autre plage horaire.

### Interprétation des résultats

- **Profit factor** (gains bruts / pertes brutes) : ≥ 1.5 est considéré comme solide, entre 1 et 1.5 la stratégie est fragile, < 1 elle est perdante.
- **Win rate** : un taux faible n'est pas rédhibitoire si le ratio gain/perte moyen compense (voir l'espérance par trade).
- **Drawdown maximum** : plus il est élevé (en valeur absolue), plus le risque de perte en capital sur une séquence défavorable est important.
- Ces indicateurs sont calculés sur un échantillon limité (7 jours en 1 minute) : ils doivent être confirmés sur une période plus longue avant toute conclusion définitive.

## Fichiers

- [backtest_real_data.py](backtest_real_data.py) — script principal (téléchargement des données, backtest, génération du graphique et du journal d'exécution).
- `mock_gold_data.csv` — données de secours utilisées si le téléchargement échoue (optionnel, à fournir localement).
- `backtest_real_performance.png` — graphique généré après exécution.
- `journal_execution_<horodatage>.log` — journal détaillé généré à chaque run (non versionné, voir `.gitignore`).

## Avertissement

Ce projet est fourni à des fins d'analyse et d'apprentissage uniquement. Il ne constitue pas un conseil en investissement.
