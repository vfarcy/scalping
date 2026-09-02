# Spécification de stratégie : Order Blocks 5 étoiles

## 1. Objectif

Identifier des Order Blocks (OB) présentant une forte confluence, attendre leur première retouche, puis entrer uniquement après une réaction confirmée du prix.

La stratégie est destinée au scalping sur des unités de temps courtes, notamment M1 et M5. Elle peut être transposée à d'autres unités de temps.

> Les affirmations de rentabilité présentées ici ne constituent pas une garantie de résultat.

## 2. Définition d'un Order Block

Un Order Block est la dernière bougie opposée avant un mouvement impulsif :

- **OB haussier** : dernière bougie baissière avant une poussée haussière agressive ;
- **OB baissier** : dernière bougie haussière avant une poussée baissière agressive.

La zone de l'OB couvre le corps de la bougie, du prix d'ouverture au prix de clôture. Une implémentation peut aussi tester une zone étendue aux mèches, mais ce choix doit être explicite et constant.

L'impulsion doit être suffisamment forte pour caractériser un déplacement institutionnel. Pour un backtest, cette notion doit être traduite par des paramètres mesurables : nombre de bougies, taille minimale du corps, distance minimale parcourue et cassure d'un niveau de structure.

## 3. Attribution des cinq étoiles

Chaque critère validé ajoute une étoile. Un OB est tradable uniquement si son score est supérieur ou égal à `min_stars`.

### Étoile 1 : imbalance / Fair Value Gap

Le mouvement créé par l'OB doit laisser une inefficience :

- pour un OB haussier, le haut de l'OB ne doit pas toucher le bas de la bougie impulsive de référence ;
- pour un OB baissier, le bas de l'OB ne doit pas toucher le haut de la bougie impulsive de référence.

La taille minimale du gap doit être exprimée en pips ou en points.

### Étoile 2 : prise de liquidité

Avant ou pendant la création de l'OB, le prix doit chasser une liquidité identifiable :

- pour un scénario haussier, un plus bas ou une zone de stops sous un creux est pris ;
- pour un scénario baissier, un plus haut ou une zone de stops au-dessus d'un sommet est pris.

Le niveau de liquidité et la fenêtre d'observation doivent être définis à l'avance dans le backtest.

### Étoile 3 : OB le plus extrême de la structure

Parmi les OB du mouvement observé :

- l'OB haussier retenu doit être celui dont le plus bas est le plus bas de la structure ;
- l'OB baissier retenu doit être celui dont le plus haut est le plus haut de la structure.

Les autres OB intermédiaires sont ignorés.

### Étoile 4 : OB non mitigé

L'OB doit être intact avant sa première retouche tradable. Toute bougie qui revient toucher la zone avant le signal constitue une mitigation et invalide l'OB pour cette entrée.

Ce critère doit être évalué uniquement avec les bougies disponibles jusqu'au moment de la confirmation. Il est interdit d'utiliser les bougies futures jusqu'à la fin du fichier pour décider si un OB historique était non mitigé.

Après une retouche ou une entrée, l'OB ne doit pas être réutilisé comme nouvelle première retouche.

### Étoile 5 : session volatile

L'OB doit être formé pendant une session considérée comme volatile :

- session européenne ;
- session américaine.

Les horaires doivent être configurables et documentés dans le fuseau horaire des données. La session asiatique est exclue par défaut dans la source.

## 4. Règles d'entrée

### Préconditions communes

1. Le score de l'OB est supérieur ou égal à `min_stars`.
2. L'OB est confirmé : l'impulsion et la cassure nécessaires sont entièrement clôturées.
3. Le prix revient pour la première fois dans la zone de l'OB.
4. Aucune position n'est déjà ouverte si la stratégie est configurée en position unique.
5. Le signal ne dépend d'aucun filtre directionnel supplémentaire tel qu'une EMA ou un retracement Fibonacci.

### Entrée BUY

1. Sélectionner un OB haussier valide.
2. Attendre que le prix retouche sa zone.
3. Attendre une réaction haussière sur l'unité d'exécution, par exemple :
   - bougie englobante haussière ;
   - marteau ou pin bar haussier.
4. Détecter le signal à la clôture de la bougie de réaction.
5. Exécuter l'achat à l'ouverture de la bougie suivante, avec spread et slippage appliqués.

### Entrée SELL

1. Sélectionner un OB baissier valide.
2. Attendre que le prix retouche sa zone.
3. Attendre une réaction baissière sur l'unité d'exécution, par exemple :
   - bougie englobante baissière ;
   - marteau inversé ou pin bar baissier.
4. Détecter le signal à la clôture de la bougie de réaction.
5. Exécuter la vente à l'ouverture de la bougie suivante, avec spread et slippage appliqués.

Une retouche sans bougie de réaction ne constitue pas une entrée.

## 5. Gestion de la position

### Stop Loss

- **BUY** : placer le Stop Loss sous la limite basse de l'OB ;
- **SELL** : placer le Stop Loss au-dessus de la limite haute de l'OB.

Une marge supplémentaire éventuelle doit être paramétrable en pips ou en points.

### Take Profit

Le ratio risque/rendement cible est de 1:2 par défaut :

$$
TP = Entry + 2 \times (Entry - SL) \quad \text{pour un BUY}
$$

$$
TP = Entry - 2 \times (SL - Entry) \quad \text{pour un SELL}
$$

Le TP doit être calculé à partir du prix d'exécution réel, après ajustement du spread.

### Break-even

Lorsque le prix atteint environ 1R, déplacer le Stop Loss vers le prix d'entrée afin de supprimer le risque nominal de la position.

Dans un backtest OHLC, si la même bougie touche le niveau 1R puis le Stop Loss, l'ordre intrabar est inconnu. Le moteur doit appliquer une convention conservatrice documentée, par exemple considérer le Stop Loss comme touché en premier.

Le spread doit être pris en compte : un déplacement exactement au prix d'entrée peut encore produire une petite perte nette.

## 6. Gestion du risque

- Capital initial : valeur configurable, fixée à `10 000 €` pour le backtest du projet.
- Risque par position : `1 %` du capital par défaut.
- Taille de position : calculée à partir de la distance entre l'entrée et le Stop Loss, du coût du spread, du slippage et de la valeur du point.
- Une position dont l'entrée est déjà située au-delà du Stop Loss doit être rejetée.
- Une position ouverte en fin de fichier doit être explicitement traitée : clôture à la dernière cotation ou exclusion documentée des statistiques.

## 7. Modèle temporel du backtest

Le moteur doit respecter l'ordre suivant :

1. analyser uniquement les bougies déjà clôturées ;
2. confirmer l'OB ;
3. surveiller les retouches futures une bougie à la fois ;
4. valider la réaction à la clôture ;
5. exécuter à l'ouverture suivante ;
6. gérer SL, TP et break-even avec une convention intrabar documentée.

Aucune fonction de détection ne doit utiliser les bougies situées après le moment où la décision aurait été disponible.

## 8. Paramètres minimaux

| Paramètre | Valeur par défaut | Rôle |
|---|---:|---|
| `min_stars` | 3 | Score minimal de l'OB |
| `risk_reward` | 2.0 | Ratio TP / risque |
| `risk_per_trade` | 1 % | Risque du capital par trade |
| `body_min_pips` | à calibrer | Taille minimale de l'impulsion |
| `break_min_pips` | à calibrer | Cassure minimale de structure |
| `fvg_min_pips` | à calibrer | Taille minimale de l'imbalance |
| session européenne | à définir | Fenêtre horaire autorisée |
| session américaine | 14h30-17h00 par défaut | Fenêtre horaire autorisée |

## 9. Journalisation obligatoire

Chaque exécution doit journaliser :

- le fichier CSV utilisé et sa période ;
- le capital initial ;
- les paramètres du run ;
- chaque OB détecté, son type, sa zone, son score et ses critères ;
- chaque mitigation ou invalidation ;
- chaque signal ;
- chaque position ouverte avec entrée, SL, TP, BOS et taille ;
- chaque sortie avec heure, prix, résultat et P&L ;
- les statistiques finales et le drawdown.

## 10. Limites et validation

Les résultats ne doivent pas être interprétés comme une preuve de rentabilité. Avant toute utilisation réelle, il faut notamment :

- tester une période plus longue et plusieurs marchés ;
- vérifier le fuseau horaire du CSV ;
- intégrer spread variable, slippage et commissions réelles ;
- contrôler les bougies dont le prix touche plusieurs niveaux dans la même minute ;
- séparer les périodes d'apprentissage, de validation et de test ;
- comparer les résultats à une stratégie de référence et à un scénario sans entrée.
