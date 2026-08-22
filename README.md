# Backtest Fibonacci OTE — Or (GC=F)

Backtest d'une stratégie de trading basée sur les zones **Fibonacci OTE (Optimal Trade Entry)** appliquée à l'or (`GC=F`), sur des données horaires réelles téléchargées depuis Yahoo Finance.

## Fonctionnement

1. **Récupération des données** : téléchargement des bougies horaires via `yfinance`. En cas d'échec (pas de connexion internet), le script se rabat automatiquement sur un fichier CSV local (`mock_gold_data.csv`).
2. **Détection de tendance** : une EMA 200 détermine le biais haussier ou baissier.
3. **Stratégie Fibonacci OTE** :
   - Identification des swings hauts/bas récents.
   - Calcul de la zone d'entrée optimale (retracement à 62 %).
   - Stop loss sous/au-dessus du swing, take profit basé sur un ratio risque/rendement.
   - Sécurisation à Break Even après cassure de structure (BOS).
4. **Résultats** : courbe d'évolution du capital, statistiques (trades gagnants/perdants/BE, win rate, profit net) et export d'un graphique PNG.

## Prérequis

```bash
pip install pandas numpy matplotlib yfinance
```

## Utilisation

```bash
python backtest_real_data.py
```

Le script :
- télécharge 1 mois de données horaires pour `GC=F`,
- exécute le backtest,
- affiche les statistiques dans la console,
- enregistre le graphique de performance sous `backtest_real_performance.png` (dans le même dossier que le script).

## Fichiers

- [backtest_real_data.py](backtest_real_data.py) — script principal (téléchargement des données, backtest, génération du graphique).
- `mock_gold_data.csv` — données de secours utilisées si le téléchargement échoue (optionnel, à fournir localement).
- `backtest_real_performance.png` — graphique généré après exécution.

## Avertissement

Ce projet est fourni à des fins d'analyse et d'apprentissage uniquement. Il ne constitue pas un conseil en investissement.
