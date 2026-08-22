# Backtest Fibonacci OTE — Or, Nasdaq, EUR/USD, Pétrole

Backtest d'une stratégie de trading basée sur les zones **Fibonacci OTE (Optimal Trade Entry)**, appliquée et comparée sur quatre actifs : l'or (`GC=F`), le Nasdaq (`NQ=F`), la paire EUR/USD (`EURUSD=X`) et le pétrole WTI (`CL=F`), sur des données réelles en 1 minute téléchargées depuis Yahoo Finance.

## Fonctionnement

1. **Récupération des données** : pour chaque actif, téléchargement des bougies en 1 minute via `yfinance` (période de 7 jours, limite maximale imposée par Yahoo Finance pour cette unité de temps). En cas d'échec (pas de connexion internet), le script se rabat automatiquement sur un fichier CSV local dédié à l'actif (ex. `mock_gold_data.csv`, `mock_nasdaq_data.csv`, `mock_eurusd_data.csv`, `mock_oil_data.csv`).
2. **Détection de tendance** : une EMA 200 détermine le biais haussier ou baissier.
3. **Stratégie Fibonacci OTE** :
   - Identification des swings hauts/bas récents.
   - Calcul de la zone d'entrée optimale (retracement à 62 %).
   - Stop loss sous/au-dessus du swing, take profit basé sur un ratio risque/rendement.
   - Sécurisation à Break Even après cassure de structure (BOS).
4. **Résultats par actif** : courbe d'évolution du capital, statistiques (trades gagnants/perdants/BE, win rate, profit net) et export d'un graphique PNG dédié.
5. **Analyse de performance** : indicateurs avancés (profit factor, gain/perte moyens, espérance par trade, drawdown maximum) accompagnés d'une interprétation textuelle automatique de la robustesse de la stratégie.
6. **Journal d'exécution** : pour chaque actif, un fichier `journal_execution_<actif>.log` est généré, détaillant le téléchargement des données, l'analyse structurelle/technique (EMA 200, swings, zone OTE) et l'exécution/protection de chaque trade (entrée, SL, TP, déclenchement du BE, résultat).
7. **Analyse par tranche horaire** : comparaison automatique de la performance (win rate, profit factor, espérance) des trades ouverts durant la session de volatilité américaine (14h30-17h00, heure de l'horodatage des données) par rapport au reste de la journée.
8. **Comparatif inter-actifs** : une fois les backtests exécutés, le script compare scientifiquement les performances de l'Or, du Nasdaq, de l'EUR/USD et du Pétrole (win rate, profit factor, drawdown maximum, profit net) via un tableau récapitulatif, un graphique `comparatif_actifs.png` et un journal `comparatif_actifs.log`.

## Prérequis

```bash
pip install pandas numpy matplotlib yfinance
```

## Utilisation

```bash
python backtest_real_data.py
```

Le script :
- télécharge les 7 derniers jours de données en 1 minute pour chacun des quatre actifs (`GC=F`, `NQ=F`, `EURUSD=X`, `CL=F`),
- exécute le backtest de la stratégie Fibonacci OTE sur chaque actif indépendamment,
- affiche les statistiques de chaque actif dans la console,
- enregistre un graphique de performance par actif (`backtest_<actif>_performance.png`) et un journal d'exécution dédié (`journal_execution_<actif>.log`),
- affiche une analyse de performance détaillée (profit factor, drawdown maximum, espérance par trade) suivie d'une interprétation qualitative de la stratégie pour chaque actif,
- compare la performance de la session de volatilité américaine (14h30-17h00) au reste de la journée, pour chaque actif,
- termine par un comparatif inter-actifs (tableau, graphique `comparatif_actifs.png`, journal `comparatif_actifs.log`) identifiant l'actif le plus performant sur la période testée.

Si le téléchargement échoue pour un actif (ex. pas de connexion), le script journalise l'erreur et poursuit avec les actifs suivants ; l'actif en échec est simplement exclu du comparatif final.

### Personnaliser la liste des actifs testés

La liste `ASSETS` définie dans le bloc `if __name__ == "__main__":` de [backtest_real_data.py](backtest_real_data.py) permet d'ajouter, retirer ou modifier les actifs comparés (ticker Yahoo Finance, période, unité de temps, fichier CSV de secours).

### Personnaliser la fenêtre horaire analysée

La fonction `analyze_session_performance(trades, session_start=(14, 30), session_end=(17, 0))` accepte des bornes personnalisées (heure, minute) si vous souhaitez comparer une autre plage horaire.

### Interprétation des résultats

- **Profit factor** (gains bruts / pertes brutes) : ≥ 1.5 est considéré comme solide, entre 1 et 1.5 la stratégie est fragile, < 1 elle est perdante.
- **Win rate** : un taux faible n'est pas rédhibitoire si le ratio gain/perte moyen compense (voir l'espérance par trade).
- **Drawdown maximum** : plus il est élevé (en valeur absolue), plus le risque de perte en capital sur une séquence défavorable est important.
- Ces indicateurs sont calculés sur un échantillon limité (7 jours en 1 minute) : ils doivent être confirmés sur une période plus longue avant toute conclusion définitive.
- Le comparatif inter-actifs permet de dégager des tendances relatives (quel actif se prête le mieux à la stratégie), mais reste soumis aux mêmes limites d'échantillon.

## Fichiers

- [backtest_real_data.py](backtest_real_data.py) — script principal (téléchargement des données, backtest multi-actifs (Or, Nasdaq, EUR/USD, Pétrole), génération des graphiques, journaux d'exécution et comparatif inter-actifs).
- `mock_gold_data.csv`, `mock_nasdaq_data.csv`, `mock_eurusd_data.csv`, `mock_oil_data.csv` — données de secours utilisées si le téléchargement échoue (optionnelles, à fournir localement).
- `backtest_<actif>_performance.png` — graphique de performance généré par actif après exécution.
- `journal_execution_<actif>.log` — journal détaillé généré par actif à chaque run (non versionné, voir `.gitignore`).
- `comparatif_actifs.png` / `comparatif_actifs.log` — graphique et journal comparant les performances des trois actifs.

## Avertissement

Ce projet est fourni à des fins d'analyse et d'apprentissage uniquement. Il ne constitue pas un conseil en investissement.

