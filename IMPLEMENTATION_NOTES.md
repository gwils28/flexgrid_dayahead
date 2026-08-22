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
