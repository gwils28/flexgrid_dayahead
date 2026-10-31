# SPEC : FlexGrid Énergie, prévision J-1 d'un portefeuille d'équilibre

Issu de l'entretien et de la passe « angles morts » faite sur les données avant d'écrire le
moindre modèle. Le brief est [`plan_flexgrid.md`](plan_flexgrid.md). Les nombres qui décident du verdict sont
figés dans [`configs/protocol.yaml`](configs/protocol.yaml), versionné avant le premier calcul de prévision.
Ce projet applique la veille [W25](https://github.com/gwils28/W25_tsfm_viability) : ses leçons sont reprises
sans être re-démontrées (piège des quantiles Bolt, AutoETS qui sélectionne un modèle plat, bootstrap par blocs
de jours, origines nombreuses plutôt que 6).

## Décisions de l'entretien

| Question | Décision |
|---|---|
| Que représente « le portefeuille » ? | Deux cibles. **(1) Le national éCO2mix**, seule série où la prévision J-1 de RTE existe : c'est là que se joue le benchmark imposé. **(2) Un portefeuille FlexGrid réel** : la somme de segments Enedis de sites tertiaires > 36 kVA (agrégats publics par région × tranche de puissance × profil, avec le nombre de sites). Les autres segments tertiaires forment le panel du router et du cold-start |
| Météo | Verdict officiel avec des **prévisions météo archivées** (Open-Meteo « Previous Runs », ECMWF IFS 0,25°), telles qu'émises avant l'heure de nomination. La météo observée (ERA5) sert à l'apprentissage et à une ablation « météo parfaite », jamais au verdict |
| Prix | Pas de token ENTSO-E. Prix day-ahead FR par l'API publique Energy-Charts. Pas de source publique sans compte pour le prix de règlement des écarts : coût d'écart par un modèle de pénalité déclaré (angle mort 8). Le client ENTSO-E est écrit et testé, activable par token |
| Mise en production | Pipeline local réel : Dagster (ingestion → features → prévision → nomination), MLflow (registre), API FastAPI des quantiles, Docker. Monitoring rejoué sur l'année de test |
| Langue | Français pour la documentation et le rapport, anglais pour les identifiants de code |
| Git | Commits par l'agent, poussés sur `gwils28/flexgrid_dayahead` (public) |

## Le portefeuille FlexGrid

Règle fixée sur l'énergie annuelle, sans regarder la difficulté de prévision : **sites tertiaires de 120 à
250 kVA, profil ENT1, des régions Centre-Val de Loire (24) et Bourgogne-Franche-Comté (27)**. Environ 3 500 sites
et 815 GWh/an, soit l'énergie du brief (800 GWh) ; le brief dit 5 000 sites, nos sites sont un peu plus gros.
Le parc de bornes de recharge du brief n'a pas d'équivalent public au pas 30 min : hors périmètre, dit ici plutôt
que simulé.

## L'horloge de la nomination

```
J-2 00:00          J-1 00:00     J-1 09:00            J 00:00                    J+1 00:00 (heure locale)
   |------------------|-------------|--------------------|---------------------------|
   [ conso Enedis connue jusqu'ici ]                     [ jour de livraison J : 46, 48 ou 50 pas noté ]
   [ conso nationale connue jusqu'à J-1 08:00 (pas qui finit à 08:30) ]
                                    ^ émission de la prévision (avant la clôture EPEX de 12:00)
```

- Une **origine** = un jour de livraison J. La prévision est émise la veille à 09:00 heure de Paris.
- National : la conso temps réel est connue jusqu'au pas de 08:00 (publication éCO2mix ~15-30 min). Horizon :
  de 08:30 J-1 à la fin de J, soit 76 pas environ ; seuls les pas de J sont notés.
- Segments Enedis : un BRP reçoit les courbes de charge de ses sites avec au moins un jour de retard ; la
  dernière observation est la fin de J-2. Horizon ~96 pas, seuls les pas de J sont notés.
- Météo : pour une heure valide de J, la prévision émise 48 h avant (`previous_day2`) est toujours publiée à
  09:00 J-1. Celle émise 24 h avant ne l'est que pour les premières heures de J : on prend 48 h partout
  (choix prudent, mesuré : erreur de température nationale 0,70 °C contre 0,65 °C à 24 h sur l'année de test).

## Angles morts trouvés avant d'écrire du code

1. **Le bug de l'heure d'été est dans la source.** Dans éCO2mix, en mars, l'heure locale 02:xx, qui n'existe
   pas, est publiée et convertie sur le même instant UTC que 03:xx : 48 horodatages UTC en double sur 2015-2026,
   dont les valeurs recopient des voisines. En octobre, une seule des deux heures 02:xx est publiée : 2 pas
   manquent chaque année. Règle : on écarte les lignes dont l'heure locale n'existe pas, on travaille en UTC, et
   le trou d'octobre est interpolé pour les entrées et jamais noté. Enedis, lui, est propre (46/50 pas les jours
   de changement).
2. **La prévision J-1 de RTE s'est dégradée en 2023 et elle est biaisée.** MAPE annuel 1,4-1,6 % de 2015 à
   2021, 2,7 % depuis 2023, avec un biais de +1,1 GW (réalisé au-dessus de la prévision) sur 2023-2026. Un biais
   stable se corrige trivialement. Battre RTE brute serait donc un résultat faible : on ajoute **RTE débiaisée**
   (moins l'erreur moyenne des 28 derniers jours connus, par demi-heure de la journée), benchmark qu'un BRP
   construirait en une ligne. Le verdict est donné contre les deux.
3. **L'alignement 15 min ↔ 30 min déplace le benchmark de 6,5 %.** Lue au quart d'heure de même horodatage, la
   prévision RTE a un MAE de 1 400 MW sur l'année de test ; lue au quart d'heure précédent, 1 310 MW. La lecture
   pré-enregistrée est « même horodatage » ; un challenger ne « bat RTE » que s'il la bat sous les deux lectures.
4. **La météo observée est une fuite d'information.** RTE nomme avec une météo prévue. Nourrir nos modèles de la
   température réalisée leur donnerait un avantage que personne n'a la veille. D'où les prévisions archivées,
   d'un modèle fixé : le défaut `best_match` d'Open-Meteo passe de GFS à ICON début 2024, une rupture silencieuse
   dans les entrées. L'archive ECMWF commence en février 2024 (rayonnement : avril 2024), ce qui fixe la fenêtre
   d'évaluation.
5. **RTE a une information que nous n'avons pas.** Sa prévision J-1 est réactualisée la veille au-delà de notre
   heure d'émission, avec sa télémesure nationale. Le benchmark est donc à l'avantage de RTE ; c'est voulu.
6. **Le MAPE national n'est pas celui d'un portefeuille.** Le national (~45 GW) moyenne des millions de sites :
   ~2,7 % de MAPE pour RTE. Un portefeuille de quelques milliers de sites est plus bruité (le brief parle de 6 %).
   Mettre le national à l'échelle de 800 GWh et le valoriser en € sous-estimerait le coût d'écart : le chiffrage
   en € principal se fait sur le portefeuille Enedis, le national mis à l'échelle est donné à titre de comparaison.
7. **L'entraînement sur météo observée, l'inférence sur météo prévue** (décalage train/serve). Un modèle supervisé
   appris sur ERA5 ignore l'erreur de prévision météo : ses intervalles seront probablement trop étroits. Mesuré,
   pas supposé ; une réparation conforme est prévue et appliquée à tous les modèles, pas au seul challenger.
8. **Pas de prix d'écart public sans compte.** Coût d'écart = volume d'écart × |prix day-ahead| × k. Avec k = 1 c'est
   la définition du brief (« volume × prix ») : la valeur de l'énergie mal placée, une borne haute. La pénalité
   réelle est un écart de prix, k = 0,1 à 0,5 en scénarios. Comme le coût est proportionnel à k, le classement des
   modèles en € ne dépend pas de k : il revient à un MAE pondéré par le prix, ce qui le distingue du MAE.
9. **Les prix changent de pas le 1er octobre 2025** (MTU 15 min du couplage européen) et 5 % sont négatifs. Les
   prix sont ramenés au pas 30 min par moyenne ; la valorisation utilise |prix| (une énergie mal placée coûte aussi
   quand le prix est négatif, dans l'autre sens).
10. **Le secret statistique d'Enedis.** Des segments ont des valeurs masquées (jusqu'à 58 % des pas) ou zéro site ;
    les tranches P3 et P7 sont des sous-totaux (les garder compterait deux fois). Panel = segments disjoints avec au
    moins 50 sites et au plus 0,5 % de pas manquants. Le nombre de sites dérive (+9 % en 3 ans sur un segment du
    portefeuille) : la cible est l'énergie totale, le nombre de sites est une covariable connue.
11. **Chronos-2 et l'apprentissage croisé.** En mode `cross_learning`, les séries d'un même lot s'informent
    mutuellement. C'est la base du « few-shot in-context » du brief, et une fuite si le lot mélange des origines
    différentes (leçon W25). Un lot ne contient donc que des séries coupées au même instant.
12. **Une seule année de test, donc un seul hiver.** Le verdict est conditionnel à l'hiver 2025-2026 ; on le dit.
    Les intervalles de confiance rééchantillonnent des blocs de 7 jours consécutifs (les 48 pas d'un jour ne sont
    pas indépendants, deux jours voisins non plus).
13. **Le lundi de Pentecôte est férié mais travaillé** (journée de solidarité) dans une partie du tertiaire. Gardé
    comme férié dans le calendrier, examiné à part dans les résidus.
14. **La MASE a besoin d'une saison d'échelle.** Saison m = 336 (hebdomadaire) au pas 30 min : c'est la naïve qu'un
    opérateur utiliserait pour un tertiaire (le lundi ne ressemble pas au dimanche). Échelle = MAE in-sample de la
    naïve hebdomadaire sur l'historique connu à l'émission.

## Périmètre

Dedans : blocs A à E du brief. Modèles : naïves (48, 336), MSTL (48, 336), AutoETS saisonnier, LightGBM global
quantile (refit hebdomadaire), Chronos-2 zero-shot sans et avec covariables, few-shot in-context sur le
cold-start, un mélange de quantiles LightGBM + Chronos-2, un router par segment. Benchmarks RTE brute et débiaisée.

Hors périmètre, nommé comme suite possible : TTM-r3 et PatchTST-FM (Chronos-2 suffit à tester la thèse TSFM ; un
second TSFM n'est ajouté que si Chronos-2 change une conclusion), le fine-tuning, les bornes de recharge, le prix
d'écart réel (token ENTSO-E ou compte RTE).

Addendum du 2026-10-16 (après la fin du projet, à la demande de l'auteur) : Timestral (Mistral AI) et TimesFM 3.0
(Google Research) entrent dans tous les blocs, avec trois jeux de covariables (aucune, météo, météo + calendrier)
et leur contexte maximal. Questions et règles dans `configs/protocol.yaml` (`addendum_2026_10_16`).

## Critères de réussite

- `flexgrid backtest` réimprime le même tableau sur deux exécutions.
- Une phrase qui dit, avec intervalle de confiance, si un modèle bat la prévision J-1 de RTE sur le national sous
  les deux alignements, et contre RTE débiaisée.
- Le coût d'écart annuel du portefeuille FlexGrid en € pour chaque modèle, et l'écart évité par rapport à la
  meilleure baseline simple, avec son intervalle.
- Le pipeline Dagster produit une nomination J-1 de bout en bout en local, servie par l'API.
- Chaque figure du rapport est produite par du code du dépôt à partir de résultats versionnés.
- `uv run pytest` vert, `uv run ruff check` propre, CI sur chaque push.

## État des critères de réussite (en fin de projet)

| Critère | État |
|---|---|
| Même tableau sur deux exécutions | Tenu : `flexgrid tables` réécrit des `results/*.csv` identiques à l'octet près (la commande s'appelle `tables`, pas `backtest` : le backtest produit les prévisions, `score` et `tables` les notent) |
| Une phrase avec IC sur RTE, deux alignements, RTE débiaisée | Tenu ([02_backtest](02_backtest/README.md)) : le mélange bat RTE publiée sous les deux lectures ; contre RTE débiaisée, pas de différence sous la lecture pré-enregistrée, défaite sous l'autre |
| Coût d'écart annuel par modèle et écart évité avec IC | Tenu ([04_cout](04_cout/README.md)), contre trois baselines simples |
| Nomination J-1 de bout en bout en local, servie par l'API | Tenu sur trois jours (46, 48 et 50 pas) ([05_production](05_production/README.md)) |
| Chaque figure produite par le code du dépôt à partir de résultats versionnés | Partiellement : verdicts, coûts, router, cold-start et dérive du concept partent de `results/`. Les figures du bloc A, la dérive des données, les profils par heure, les éventails et le coût par heure lisent les données ou les prévisions brutes (non versionnées) : elles se refont après `make data` et le backtest |
| `pytest` vert, `ruff` propre, CI | Tenu |
| Addendum : un nouveau TSFM bat-il Chronos-2, le calendrier aide-t-il, le service change-t-il ? | Tranché ([02_backtest](02_backtest/README.md#addendum-du-2026-10-16-timestral-et-timesfm)) : non à contexte égal, oui pour Timestral à contexte long (national) ; le calendrier aide surtout Chronos-2 ; le service garde le mélange d'origine |
