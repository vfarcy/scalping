# Backtest Fibonacci OTE

Ce projet teste une stratégie de scalping basée sur le retracement de Fibonacci **OTE (Optimal Trade Entry)**. Le signal est filtré par une moyenne mobile exponentielle 200, protégé par un Stop Loss, puis géré avec un Take Profit à ratio risque/rendement 1:2 et une sécurisation au Break Even après cassure de structure.

Le script principal est [scalping.py](scalping.py). Il compare actuellement l'or (`GC=F`), le Nasdaq (`NQ=F`), EUR/USD (`EURUSD=X`) et le pétrole WTI (`CL=F`) à partir de données Yahoo Finance en 1 minute.

## Logique de la stratégie

### 1. Données et préparation

Pour chaque actif, `download_or_load_data()` tente de télécharger les bougies avec `yfinance`. Une bougie contient au minimum `time`, `open`, `high`, `low` et `close`.

Yahoo Finance limite généralement l'historique en 1 minute à environ 7 jours. Si le téléchargement échoue et qu'un fichier de secours existe, le script utilise le CSV correspondant à l'actif. Les horaires sont convertis vers `America/New_York` par `normalize_to_market_timezone()` lorsque les timestamps possèdent un fuseau.

### 2. Filtre de tendance EMA 200

Le code calcule une EMA 200 sur les clôtures :

```text
EMA actuelle = alpha * clôture actuelle + (1 - alpha) * EMA précédente
alpha = 2 / (200 + 1)
```

- Si `close > EMA 200`, seuls les scénarios acheteurs (`BUY`) sont recherchés.
- Si `close < EMA 200`, seuls les scénarios vendeurs (`SELL`) sont recherchés.
- Si le cours est exactement égal à l'EMA, aucun des deux scénarios n'est sélectionné.

L'EMA donne un biais directionnel ; elle ne constitue pas à elle seule un signal d'entrée.

### 3. Construction du mouvement impulsif

À chaque bougie, le code observe les `window * 2` bougies précédentes. Avec `window=20`, cela représente au maximum 40 bougies, sans utiliser la bougie en cours pour construire les niveaux.

Pour un achat :

1. `start_point` est le plus bas de la fenêtre.
2. `end_point` est le plus haut de la fenêtre.
3. Le plus bas doit apparaître avant le plus haut.
4. L'amplitude doit dépasser `0,05 %` du prix courant.

Pour une vente, la logique est inversée : le plus haut doit apparaître avant le plus bas.

Cette méthode utilise les extrêmes de la fenêtre récente. Elle est volontairement simple : les colonnes `swing_high` et `swing_low` sont calculées mais les niveaux effectivement utilisés proviennent directement des extrêmes de la fenêtre.

### 4. Entrée OTE à 62 %

L'OTE est le retracement de 62 % du mouvement identifié.

Pour un achat, avec `diff = end_point - start_point` :

```text
entrée OTE = end_point - 0,62 * diff
```

Pour une vente, avec `diff = start_point - end_point` :

```text
entrée OTE = end_point + 0,62 * diff
```

Le signal est validé lorsque la mèche de la bougie atteint la zone OTE et que la clôture reste du bon côté du Stop Loss :

- achat : `low <= ote_entry` et `close > sl` ;
- vente : `high >= ote_entry` et `close < sl`.

Le code ne simule pas une entrée immédiate au prix OTE. Il enregistre un signal, puis tente l'entrée à l'ouverture de la bougie suivante. Si cette ouverture est défavorable ou se trouve de l'autre côté du Stop Loss, le signal est ignoré.

### 5. Stop Loss, BOS et Take Profit

Pour un achat :

```text
SL = start_point - 0,02 * diff
BOS = end_point
TP = entrée + (entrée - SL) * risk_reward
```

Pour une vente :

```text
SL = start_point + 0,02 * diff
BOS = end_point
TP = entrée - (SL - entrée) * risk_reward
```

Le paramètre `risk_reward=2.0` donne un objectif théorique de deux unités de risque. Le filtre de 2 % est calculé sur l'amplitude du mouvement, et non sur un pourcentage fixe du prix.

Lorsqu'un achat atteint le BOS par son plus haut, ou qu'une vente l'atteint par son plus bas, le SL est déplacé au prix d'entrée et `be_triggered` passe à `True`. Une sortie ultérieure sur ce niveau est classée `BE`.

Si une même bougie touche le SL et le TP, le code vérifie le SL en premier. Cette convention est prudente, mais elle ne permet pas de connaître l'ordre intrabougie réel avec des données en 1 minute.

## Gestion du risque et des coûts

Le capital initial vaut `10 000 €` et le risque par trade vaut par défaut `1 %` du capital disponible. La taille de position est calculée à l'ouverture :

```text
risque monétaire = capital * risk_per_trade
coût unitaire = spread + 2 * slippage
risque par unité = (distance SL + coût unitaire) * point_value
taille = risque monétaire / risque par unité
```

Le P&L dépend donc de la distance réelle entre l'entrée, la sortie et le SL. Il n'est plus fixé artificiellement à `-100 €` ou `+200 €`.

Les paramètres de `run_fibonacci_backtest()` sont :

- `risk_per_trade=0.01` : 1 % du capital par trade ;
- `spread=0.0` : spread exprimé dans l'unité de prix ;
- `slippage=0.0` : glissement par côté, dans l'unité de prix ;
- `commission=0.0` : commission fixe déduite à la sortie ;
- `point_value=1.0` : valeur monétaire d'une unité de variation.

### Cas d'un compte Axi Standard

Sur un compte Axi Standard, la commission séparée est généralement nulle et le coût principal est le spread. Il faut donc conserver `commission=0.0` et renseigner un spread réaliste pour chaque instrument, idéalement mesuré dans l'historique des cotations Axi.

Exemple indicatif pour EUR/USD avec un spread moyen de 1,2 pip :

```python
{'label': 'EUR/USD', 'ticker': 'EURUSD=X', 'spread': 0.00012, 'slippage': 0.00002}
```

Cette valeur est seulement un exemple : le spread Axi varie selon la liquidité, l'heure et les annonces. Les tickers Yahoo (`GC=F`, `NQ=F`, `CL=F`) sont des contrats futures et ne reproduisent pas exactement les CFD Axi. Le spread et le `point_value` doivent donc être calibrés séparément pour chaque instrument.

## Déroulement d'un trade

1. Une clôture valide la tendance et les conditions OTE.
2. Le signal est stocké dans `pending_trade`.
3. À la bougie suivante, l'ouverture devient le prix d'entrée réel.
4. Le signal est refusé si l'ouverture est déjà au-delà du SL.
5. La taille de position est calculée selon le capital et la distance du SL.
6. Chaque nouvelle bougie vérifie d'abord le Break Even, puis le SL, puis le TP.
7. Le capital est mis à jour à la clôture du trade.
8. Une valeur de capital est enregistrée à chaque bougie pour calculer la courbe et le drawdown.

Un seul trade peut être ouvert à la fois. Le code ne prend pas en compte les ordres partiellement exécutés, les positions simultanées, les appels de marge ou les écarts de cotation entre le signal et l'exécution réelle.

## Statistiques produites

- **Win rate** : nombre de `WIN` divisé par le nombre total de trades, BE compris.
- **Profit factor** : gains bruts divisés par pertes brutes.
- **Espérance** : P&L moyen par trade.
- **Drawdown maximum** : baisse maximale de la courbe de capital par rapport à son sommet précédent.
- **Profit net** : capital final moins capital initial.

Le win rate ne doit pas être interprété seul. Avec un ratio cible 1:2, une stratégie peut être rentable avec moins de 50 % de trades gagnants, mais les frais, le spread et le slippage augmentent le seuil de rentabilité.

L'analyse par session compare les trades ouverts entre 14h30 et 17h00, heure de New York, au reste de la journée. Une session contenant très peu de trades ne permet pas de conclure statistiquement ; un résultat positif sur un seul trade est un signal descriptif, pas une preuve de supériorité.

## Installation et exécution

```bash
pip install pandas numpy matplotlib yfinance
python scalping.py
```

Le script télécharge les données des quatre actifs, exécute un backtest indépendant pour chacun, affiche les statistiques dans la console et génère :

- `backtest_<actif>_performance_<timestamp>.png` ;
- `journal_execution_<actif>_<timestamp>.log` ;
- `comparatif_actifs_<timestamp>.png` ;
- `comparatif_actifs_<timestamp>.log`.

Une erreur de téléchargement sur un actif est journalisée ; le script poursuit les autres actifs et exclut l'actif sans résultat du comparatif final.

## Personnalisation

La liste `ASSETS`, dans le bloc `if __name__ == "__main__":` de [scalping.py](scalping.py), permet de modifier les tickers, périodes, fichiers CSV de secours, spreads et slippages.

La fonction `run_fibonacci_backtest()` permet aussi de modifier directement `window`, `risk_reward`, `initial_capital`, `risk_per_trade`, `spread`, `commission`, `slippage` et `point_value`.

La plage horaire analysée se personnalise avec `analyze_session_performance(trades, session_start=(14, 30), session_end=(17, 0))`.

## Limites à traiter avant une utilisation réelle

- La fenêtre Yahoo en 1 minute est courte ; il faut tester plusieurs mois avec une source adaptée.
- Les données Yahoo ne sont pas les cotations bid/ask Axi et ne reproduisent pas exactement le spread du broker.
- Le backtest ne connaît pas l'ordre réel des mouvements à l'intérieur d'une bougie.
- Le `point_value` par défaut vaut `1.0` et doit être adapté au contrat ou à l'unité négociée.
- Les coûts doivent être renseignés pour obtenir un résultat net crédible.
- La taille peut devenir excessive si la distance du SL est très faible ; une taille maximale et une distance minimale devraient être ajoutées.
- Il faut séparer les données d'optimisation et de validation afin de limiter le surajustement.
- Les résultats passés ne garantissent pas les résultats futurs.

Ce projet est fourni à des fins d'analyse et d'apprentissage uniquement. Il ne constitue pas un conseil en investissement.
