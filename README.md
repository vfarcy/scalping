# Backtest Fibonacci OTE

Ce dépôt contient un backtest en Python de la stratégie Fibonacci OTE sur plusieurs actifs financiers, avec génération de journaux d’exécution détaillés et de statistiques comparatives.

Le script principal est [backtest_real_data.py](backtest_real_data.py). Il télécharge les données Yahoo Finance en 1 minute, applique la logique OTE + EMA 200 + BOS, puis produit des résultats et des journaux par actif.

## Actifs actuellement testés

- Or : `GC=F`
- Nasdaq : `NQ=F`
- EUR/USD : `EURUSD=X`
- Pétrole WTI : `CL=F`

## État actuel de la stratégie

Les résultats récents indiquent que :

- L’or est le seul actif clairement rentable sur la période testée.
- EUR/USD est marginalement positif mais très fragile.
- Nasdaq et pétrole sont négatifs sur la même période.

La synthèse détaillée est disponible dans [strategie_fibonacci_ote_synthese.md](strategie_fibonacci_ote_synthese.md).

## Dépendances

```bash
pip install pandas numpy matplotlib yfinance
```

## Exécution

```bash
python backtest_real_data.py
```

Le script génère des journaux du type :

- `journal_execution_or_gold_YYYYMMDD_HHMMSS.log`
- `journal_execution_eurusd_YYYYMMDD_HHMMSS.log`
- `journal_execution_nasdaq_YYYYMMDD_HHMMSS.log`
- `journal_execution_pétrole_wti_YYYYMMDD_HHMMSS.log`

## Ce que fait la stratégie

- calcul d’une EMA 200 pour le biais de tendance ;
- détection de mouvement impulsif sur une fenêtre glissante ;
- entrée sur retracement OTE à 62 % ;
- stop loss, take profit et sécurisation Break Even au BOS ;
- calcul du P&L, du win rate, du profit factor, du drawdown et du profit net.

## Limites importantes

- Les résultats sont encore basés sur une période courte (7 jours en 1 minute).
- Le spread, le slippage et les frais réels ne sont pas encore calibrés comme dans un environnement de trading réel.
- Les performances varient fortement selon l’actif ; il faut donc valider chaque instrument séparément avant toute utilisation commerciale.

## Objectif du projet

Le but de ce dépôt est de tester la robustesse de la logique Fibonacci OTE, d’évaluer son comportement par actif, puis de cibler les marchés qui méritent un calibrage plus avancé avant un usage opérationnel.


- La fenêtre Yahoo en 1 minute est courte ; il faut tester plusieurs mois avec une source adaptée.
- Les données Yahoo ne sont pas les cotations bid/ask Axi et ne reproduisent pas exactement le spread du broker.
- Le backtest ne connaît pas l'ordre réel des mouvements à l'intérieur d'une bougie.
- Le `point_value` par défaut vaut `1.0` et doit être adapté au contrat ou à l'unité négociée.
- Les coûts doivent être renseignés pour obtenir un résultat net crédible.
- La taille peut devenir excessive si la distance du SL est très faible ; une taille maximale et une distance minimale devraient être ajoutées.
- Il faut séparer les données d'optimisation et de validation afin de limiter le surajustement.
- Les résultats passés ne garantissent pas les résultats futurs.

Ce projet est fourni à des fins d'analyse et d'apprentissage uniquement. Il ne constitue pas un conseil en investissement.
