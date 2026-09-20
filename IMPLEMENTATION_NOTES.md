# Notes d'implémentation

Déviations par rapport au brief et à `SPEC.md`, choix prudents, et affirmations corrigées par une mesure. Les plus
récentes en dernier.

## Bloc A : données

- **DÉVIATION (2026-08-21, avant toute prévision) : contrôle de plage des segments.** La règle pré-enregistrée
  [0,05 ; 5] × médiane retirait 7 399 pas réels de 84_P4_ENT1 (et 1 144 de 93_P4_ENT1, 106 de 76_P4_ENT1) : des
  segments chauffés à l'électricité dont l'hiver vaut 6 fois l'été. Remplacée par [0,05 × médiane ; 2 × q99,9 %],
  qui ne retire aucun pas. Valeur d'origine conservée dans le protocole.
- Le chiffre météo du SPEC (« 0,70 °C à 48 h ») a été mesuré sur les valeurs horaires ; au pas 30 min, après
  interpolation, c'est 0,69 °C (contre 0,65 °C à 24 h). Les README citent la valeur au pas 30 min.
- Le prix day-ahead est mis au pas 15 min par répétition de la valeur horaire avant le 1er octobre 2025, puis moyenné
  au pas 30 min : une moyenne de deux quarts d'heure identiques avant cette date, de deux prix différents après.
- La moyenne météo du portefeuille donne le même poids aux deux régions (Orléans, Dijon) : leurs segments ont des
  énergies voisines (413 et 403 GWh/an).
- Le manifeste `data/MANIFEST.json` garde la date réelle de chaque téléchargement.

## Bloc B : modèles

- **Fuite trouvée par un test avant tout calcul : les retards en pas UTC.** Un retard de 2 jours compté en pas
  (96 pas = 48 h) lit, pour les derniers pas du jour du passage à l'heure d'hiver, la valeur de 00:30 locale en J-1 :
  après le cutoff des segments (fin de J-2). Les retards (2, 7, 14 jours) et la température d'il y a 7 jours sont
  désormais pris à la même heure d'horloge locale (`features.local_shift`). Le test garde aussi la version UTC pour
  vérifier qu'elle fuit bien : s'il cessait d'échouer, c'est que le test ne testerait plus rien.
- **DÉVIATION (2026-08-27, avant toute prévision) : sous-échantillonnage des lignes de LightGBM.** Le panel compte
  4,25 M lignes d'apprentissage ; un quantile prend 55 s, soit ~8 h pour 78 réapprentissages hebdomadaires x 7
  quantiles. `bagging_fraction = 0,3` ramène un quantile à 26 s. Appliqué aux deux familles.
- Le calendrier est précalculé une fois sur 2014-2027 et lu par position : le `reindex` d'un index UTC dont l'unité
  diffère (`datetime64[us]` contre `[ns]`) coûtait 80 ms par appel, et il y en a 45 000.
- Chronos-2 est entraîné sur 21 quantiles de 0,01 à 0,99 : la grille du protocole (0,05 à 0,95) est native, pas le
  piège de Chronos-Bolt vu dans W25.
- Les modèles statistiques reçoivent les pas imputés comme entrées (le trou d'octobre), jamais comme cibles.

## Bloc C : backtest

- **Affirmation corrigée par une mesure : la sous-couverture de LightGBM.** L'angle mort 7 du SPEC l'attribuait au
  décalage train/serve (météo observée à l'apprentissage, prévue à l'inférence). Avec la météo observée en entrée, la
  couverture 90 % reste à 0,77 (0,76 avec la météo prévue) : la cause principale est la régression quantile, qui
  s'ajuste à ses données d'apprentissage. Le SPEC n'est pas réécrit ; la correction est ici et au README du bloc C.
- **Ajout non pré-enregistré, déclaré comme tel : le benchmark `rte_prorata`** pour le portefeuille (prévision RTE
  nationale multipliée par la part moyenne du portefeuille, par demi-heure locale, sur les 28 jours connus jusqu'à
  J-2 ; la part absorbe au passage le biais de RTE). RTE ne publie rien à
  l'échelle d'un portefeuille ; sans ce benchmark, la seule référence du portefeuille serait une naïve. Il est
  ajouté comme référence supplémentaire et ne remplace aucun critère.
- La réparation conforme utilise les erreurs des 56 origines précédentes : elle suit les saisons avec retard. En
  novembre-décembre, quand l'erreur monte vite, la couverture réparée tombe sous la bande. C'est une propriété de
  la fenêtre, pas un bug ; une fenêtre plus courte suivrait mieux mais serait plus bruitée.
- Les prévisions brutes (`results/forecasts/`) ne sont pas versionnées (plusieurs centaines de Mo) ; les tableaux
  par origine (`results/per_origin_*.parquet`) le sont, et toutes les figures et tous les verdicts en partent.
- Sursouscription des cœurs : LightGBM (32 threads) lancé en même temps qu'un autre calcul LightGBM a multiplié la
  durée par plus de 5. Les calculs lourds sont lancés l'un après l'autre.

## Bloc E : monitoring

- **Un seuil d'alerte naïf est inutilisable.** « Alerter quand le MAE glissant sur 28 jours dépasse celui de RTE
  débiaisée » aurait sonné 208 jours sur 365 pour le mélange et 215 pour LightGBM (alerte = 14 jours consécutifs
  au-dessus). Le modèle est moins bon que RTE débiaisée hors de l'été et de l'automne : le seuil décrit un état connu, il ne
  détecte rien. Le seuil retenu est auto-référencé : 1,15 fois le ratio médian du modèle sur la validation
  (février-juin 2025), 14 jours consécutifs au-dessus. Il donne 52 jours d'alerte pour le mélange, 12 pour LightGBM.
