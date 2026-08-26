# Synthèse de performance — stratégie Fibonacci OTE

## 1) Résultat global par actif

| Actif | Win rate | Profit factor | Espérance / trade | Profit net | Drawdown max |
|---|---:|---:|---:|---:|---:|
| Or (GC=F) | 38,5 % | 1,42 | +24,93 € | +2 268,66 € | -5,04 % |
| EUR/USD (EURUSD=X) | 27,6 % | 1,05 | +3,03 € | +87,75 € | -10,84 % |
| Pétrole (CL=F) | 27,1 % | 0,85 | -8,44 € | -404,95 € | -8,81 % |
| Nasdaq (NQ=F) | 22,5 % | 0,69 | -17,68 € | -1 573,21 € | -19,17 % |

## 2) Conclusion

La stratégie est rentable uniquement sur l’or dans cette période de test.

- L’or est le seul actif qui montre une vraie rentabilité avec un profit factor > 1 et un drawdown maîtrisé.
- EUR/USD est à peine positif, mais trop fragile pour être considéré comme validé : le profit factor reste proche de 1 et l’espérance par trade est faible.
- Le pétrole et le Nasdaq sont nettement négatifs et ne sont pas adaptés à cette configuration actuelle de la stratégie.

## 3) Verdict décisionnel

### Actif à prioriser
- Or (GC=F)

### Actifs à revoir / ne pas utiliser en production pour l’instant
- EUR/USD : à tester avec un filtrage plus strict et sur une période plus longue
- Pétrole : non rentable sur cette période
- Nasdaq : non rentable et drawdown élevé

## 4) Recommandation pratique

1. Conserver la stratégie uniquement sur l’or pour le moment.
2. Revoir le calibrage sur EUR/USD avant toute mise en live.
3. Écarter le pétrole et le Nasdaq tant que le modèle n’est pas revalidé.
4. Vérifier, sur une période plus longue, l’impact réel du spread, des frais et du slippage avant toute exploitation commerciale.

## 5) Synthèse courte

Le backtest montre que la stratégie Fibonacci OTE est viable sur l’or, mais pas encore robuste sur les autres actifs testés. La rentabilité sur l’or est suffisamment claire pour justifier un focus, tandis que EUR/USD, pétrole et Nasdaq nécessitent une refonte ou un filtrage plus strict.
