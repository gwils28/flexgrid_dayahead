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
