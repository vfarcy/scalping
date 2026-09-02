# Backtest Order Blocks EUR/USD M1

Ce projet backteste une stratégie d'Order Blocks sur les données historiques EUR/USD en unité M1.

Le script de référence est [backtest_order_blocks_strategy.py](backtest_order_blocks_strategy.py). Il utilise uniquement le fichier CSV local [EURUSD_M1_202605270610_202609011829.csv](EURUSD_M1_202605270610_202609011829.csv) et un capital initial de `10 000 EUR`.

La spécification détaillée de la stratégie est disponible dans [strategie_order_blocks_specification.md](strategie_order_blocks_specification.md).

Le dépôt contient deux scripts Python. Ils ne produisent pas des résultats comparables : ils appliquent deux modèles différents et doivent être exécutés séparément.

## Scripts Python

### `backtest_order_blocks_strategy.py`

Script de référence du projet. Il applique la stratégie Order Blocks 5 étoiles au CSV EUR/USD M1 local, avec un capital initial de `10 000 EUR`. Son fonctionnement et ses sorties sont décrits dans les sections ci-dessous.

### `backtest_real_data.py`

Script complémentaire de comparaison multi-actifs. Il applique l'ancien modèle Fibonacci OTE avec filtre EMA 200 et tente de télécharger des données via `yfinance` pour :

- Or (`GC=F`) ;
- Nasdaq (`NQ=F`) ;
- EUR/USD (`EURUSD=X`) ;
- Pétrole WTI (`CL=F`).

Il normalise les timestamps lorsque le fournisseur fournit un fuseau horaire, exécute un backtest indépendant par actif, puis génère un comparatif. En cas d'échec du téléchargement, il utilise un CSV de secours si celui-ci existe. Ce script n'utilise pas le CSV EUR/USD M1 de référence et ses résultats ne doivent pas être mélangés à ceux du script Order Blocks.

Exécution :

```powershell
mamba run -n scalping_env python .\backtest_real_data.py
```

Ce script peut nécessiter un accès réseau et la dépendance `yfinance`, contrairement au backtest local Order Blocks.

## Environnement

L'environnement Python est défini dans [environment.yml](environment.yml).

Avec Mamba :

```powershell
mamba env create -f environment.yml
mamba activate scalping_env
```

Si l'environnement existe déjà :

```powershell
mamba activate scalping_env
```

Dépendances principales :

- Python 3.11 ;
- pandas ;
- numpy.

## Exécution

Depuis le dossier du projet :

```powershell
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py
```

Le seuil minimal est de 3 étoiles par défaut. Pour le modifier :

```powershell
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py --min-stars 2
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py --min-stars 4
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py --min-stars 5
```

Le chemin du CSV peut être remplacé avec `--csv` :

```powershell
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py --csv .\EURUSD_M1_202605270610_202609011829.csv
```

Un chemin de log explicite peut être fourni avec `--log` :

```powershell
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py --log .\resultat_order_blocks.log
```

## Règles appliquées

### Order Block

- OB haussier : dernière bougie baissière avant deux bougies haussières ;
- OB baissier : dernière bougie haussière avant deux bougies baissières ;
- confirmation après la clôture des deux bougies d'impulsion ;
- zone de l'OB : corps de la bougie, entre ouverture et clôture ;
- corps minimal de la première bougie d'impulsion : `2 pips` ;
- cassure minimale du niveau de l'OB : `2 pips`.

### Étoiles

Un OB reçoit une étoile pour chacun des critères suivants :

1. imbalance/FVG d'au moins `0,5 pip` ;
2. prise de liquidité sur les `6` bougies précédentes ;
3. OB situé à l'extrême de la structure récente, sur une fenêtre de `20` bougies ;
4. zone intacte au moment de la confirmation ;
5. formation pendant une session volatile européenne ou américaine.

Seuls les OB dont le score est supérieur ou égal à `--min-stars` sont tradables.

La détection est causale : le statut non mitigé n'utilise pas les bougies futures jusqu'à la fin du fichier. Après confirmation, les retouches sont vérifiées une bougie à la fois.

### Entrée

Une position exige toutes les conditions suivantes :

1. un OB valide ayant au moins le seuil d'étoiles demandé ;
2. une première retouche de sa zone ;
3. une réaction dans le sens de l'OB : englobante ou marteau/pin bar ;
4. retouche du niveau Fibonacci `62 %` du mouvement impulsif associé ;
5. aucune position déjà ouverte.

Le signal est détecté à la clôture de la bougie de réaction et l'entrée est exécutée à l'ouverture de la bougie suivante.

Le Fibonacci ne remplace pas l'Order Block : il sert uniquement à choisir le moment de l'entrée.

### Gestion de la position

- risque par trade : `1 %` du capital courant ;
- capital initial : `10 000 EUR` ;
- BUY : Stop Loss sur la limite basse du corps de l'OB ;
- SELL : Stop Loss sur la limite haute du corps de l'OB ;
- Take Profit : ratio risque/rendement `1:2` ;
- break-even : déplacement du Stop Loss à l'entrée après un mouvement favorable de `1R` ;
- une position encore ouverte à la fin du CSV est clôturée au dernier cours et classée `END`.

Le spread est lu dans la colonne `<SPREAD>` du CSV et converti en prix avec `1 point = 0,00001` pour EUR/USD. Le slippage et la commission sont nuls par défaut dans ce script.

## Format du CSV

Le fichier doit être un export MetaTrader 5 séparé par tabulations avec au minimum les colonnes :

```text
<DATE> <TIME> <OPEN> <HIGH> <LOW> <CLOSE> <SPREAD>
```

Les colonnes sont normalisées en minuscules. Les champs `DATE` et `TIME` sont combinés dans la colonne `time`.

Les horaires du CSV sont utilisés tels quels. Le script ne convertit pas automatiquement le fuseau horaire. Les sessions européennes et américaines doivent donc être interprétées dans le fuseau réellement utilisé par l'export MT5.

## Fichiers générés

Chaque exécution produit un journal nommé :

```text
backtest_order_blocks_YYYYMMDD_HHMMSS.log
```

Le journal contient :

- le chemin du CSV utilisé ;
- le capital initial ;
- les paramètres du run ;
- le nombre d'Order Blocks retenus ;
- le détail de chaque trade ;
- le résultat `WIN`, `LOSS`, `BE` ou `END` ;
- le P&L de chaque position ;
- la répartition de la volatilité de `00h` à `23h` ;
- l'amplitude moyenne et médiane par heure ;
- la part de chaque heure dans l'amplitude totale ;
- le bilan financier final.

Le résumé final est également imprimé dans la console :

```text
=== RESULTAT FINAL UNIQUE ===
CSV source          : ...
Capital initial     : 10000.00 EUR
Order Blocks retenus: ...
Trades clôturés     : ...
WIN / LOSS / BE / END : ...
Capital final       : ... EUR
Profit net          : ... EUR
Drawdown maximum    : ...%
Journal             : ...
```

## Validation

Compiler le script :

```powershell
mamba run -n scalping_env python -m py_compile .\backtest_order_blocks_strategy.py
```

Puis exécuter le backtest :

```powershell
mamba run -n scalping_env python .\backtest_order_blocks_strategy.py --min-stars 3
```

Les résultats ne doivent être comparés qu'entre exécutions utilisant le même CSV, les mêmes paramètres et le même capital initial. Les anciens logs ou sorties provenant d'autres scripts ne sont pas des résultats de référence.

## Limites

- Les données M1 ne permettent pas de connaître l'ordre exact des mouvements à l'intérieur d'une bougie ;
- le fuseau horaire du CSV doit être vérifié manuellement ;
- le backtest utilise le spread historique de la bougie du signal, mais ne modélise pas toutes les conditions d'exécution d'un broker ;
- quatre trades ou quelques dizaines de trades ne suffisent pas à établir la robustesse d'une stratégie ;
- les résultats historiques ne garantissent aucun résultat futur ;
- ce projet est destiné à l'analyse et à l'apprentissage, pas à constituer un conseil financier.

## Fichiers principaux

- [backtest_order_blocks_strategy.py](backtest_order_blocks_strategy.py) : script de backtest de référence ;
- [backtest_real_data.py](backtest_real_data.py) : comparaison multi-actifs basée sur le modèle Fibonacci OTE/EMA 200 ;
- [strategie_order_blocks_specification.md](strategie_order_blocks_specification.md) : règles détaillées de la stratégie ;
- [EURUSD_M1_202605270610_202609011829.csv](EURUSD_M1_202605270610_202609011829.csv) : données EUR/USD M1 utilisées ;
- [environment.yml](environment.yml) : environnement Python du projet.
