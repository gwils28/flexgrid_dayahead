# Blocs B et C : modèles et backtest

Rolling-origin sur **365 jours de livraison** (1er juillet 2025 → 30 juin 2026), prévision émise chaque veille à
9 h, précédés de 181 jours de validation (janvier-juin 2025) qui servent au router et à la calibration conforme.
Commandes : `flexgrid forecast <famille> <modèles>`, puis `flexgrid score national segments`. Les nombres viennent
de `results/summary_national.csv` et `results/verdicts_national.csv`.

## La réponse en une phrase (national)

> Nos meilleurs modèles battent nettement la prévision J-1 publiée par RTE : le mélange LightGBM + Chronos-2 a un
> MAE de 897 MW contre 1 400 MW (ratio 0,64, IC 95 % [0,56 ; 0,73]), sous les deux lectures du quart d'heure, avec
> une couverture 90 % de 0,86, dans la bande pré-enregistrée. **Mais une correction de biais d'une ligne appliquée à
> RTE fait mieux que tous nos modèles** : 816 MW. Contre elle, le mélange ne montre « pas de différence »
> (1,10 [0,99 ; 1,22]) sous la lecture pré-enregistrée, et **perd** sous la lecture favorable à RTE (1,14 [1,02 ; 1,26]).

Le critère du brief, « battre la prévision J-1 de RTE », est donc rempli au sens littéral et ne l'est pas au sens
utile. Le sens utile est le seul qui compte pour un BRP : il peut corriger RTE lui-même. Sur le national, la valeur
démontrable de nos modèles ne vient pas de la précision ponctuelle, elle vient de :
- **l'été**, où le mélange bat RTE débiaisée (592 MW contre 706 MW de juillet à octobre) ;
- **les quantiles**, que RTE ne publie pas ;
- **le portefeuille**, où RTE n'existe pas (section suivante).

![Qui bat RTE](figures/national_forest.png)

## Ce que montre chaque figure

### L'erreur selon l'heure

![MAE par heure](figures/national_by_hour.png)

La prévision RTE brute (tirets noirs) a la signature de son biais : des pics à 00:30, 12:30-13:30 et un plateau
l'après-midi, ceux vus au bloc A. Débiaisée (tirets gris), elle est la meilleure courbe de 7 h à 13 h, quand les
usages tertiaires démarrent. Nos modèles ne voient la conso nationale que jusqu'à 8 h la veille ; RTE, elle, révise
sa prévision plus tard et avec sa propre télémesure (SPEC, angle mort 5). La nuit, le mélange fait jeu égal.

### Mois par mois

![Ratio mensuel](figures/national_monthly.png)

Sous 1, le modèle fait mieux que RTE débiaisée. Le mélange gagne d'août à octobre et en juin, perd tout l'hiver et
au printemps. Sur l'année, il fait mieux qu'elle un jour sur deux (50,7 % des jours) mais perd en moyenne : ses
mauvais jours sont des jours d'hiver, où les erreurs se comptent en GW. L'hiver est la saison où une erreur de température coûte le plus (2 à 3 GW par degré en France) ; c'est
aussi celle où l'information fraîche de RTE vaut le plus. En avril-mai, RTE brute se dégrade (ratio 2,7) : son biais
augmente, et la correction glissante sur 28 jours le suit.

### Par type de jour

![Par type de jour](figures/national_day_types.png)

Chronos-2, même informé des fériés par une covariable, se trompe lourdement les jours fériés (ratio 2,25 contre RTE
débiaisée, n = 11). LightGBM, qui a vu dix ans de fériés dans son apprentissage, est le seul à faire jeu égal ces
jours-là (0,97). Le jour de Noël ci-dessous le montre : Chronos-2 prévoit presque un jeudi ordinaire.

![Trois jours](figures/national_fans.png)

### Les intervalles

![Calibration](figures/national_calibration.png)

- **LightGBM brut est trop sûr de lui** : son intervalle 90 % ne couvre que 76 % des pas. L'angle mort 7 du SPEC
  annonçait un décalage train/serve (appris sur météo observée, utilisé sur météo prévue). Le décalage existe, mais
  il n'explique pas tout : avec la météo observée en entrée, la couverture n'est que de 77 %. L'essentiel vient de la
  régression quantile elle-même, qui s'ajuste trop bien à ses données d'apprentissage.
- Le mélange couvre 86 % (dans la bande), Chronos-2 avec covariables 83 %.
- **La réparation conforme** (médiane conservée, quantiles reconstruits sur les erreurs des 56 derniers jours)
  ramène tous les modèles à 0,906-0,908. Appliquée à RTE débiaisée, elle donne la meilleure pinball loss du national
  (238 MW contre 267 pour le mélange) : sur le national, même la prévision probabiliste la plus utile est une RTE
  corrigée.

### La météo parfaite n'aurait presque rien changé

![Météo parfaite](figures/national_oracle_weather.png)

Les mêmes modèles LightGBM, nourris avec la météo observée au lieu de la météo prévue 48 h avant, ne gagnent que
4 % de MAE (933 contre 972 MW). L'erreur de prévision météo n'est donc pas ce qui sépare nos modèles de RTE.
Ce qui les sépare, c'est l'information sur la conso elle-même : à quelle heure on la connaît, et à quel niveau de
détail.

## Les autres modèles

| Modèle | MAE (MW) | MAPE | MASE | couverture 90 % |
|---|---|---|---|---|
| RTE J-1 débiaisée | 816 | 1,61 % | 0,233 | (ponctuelle) |
| Mélange LightGBM + Chronos-2 | 897 | 1,73 % | 0,256 | 0,857 |
| LightGBM | 972 | 1,87 % | 0,277 | 0,758 |
| Chronos-2 + covariables | 1 109 | 2,15 % | 0,316 | 0,826 |
| RTE J-1 publiée | 1 401 | 2,79 % | 0,399 | (ponctuelle) |
| Chronos-2 sans covariables | 1 752 | 3,33 % | 0,499 | 0,811 |
| MSTL | 2 284 | 4,47 % | 0,651 | 0,786 |
| Naïve J-1, naïve S-1, ETS saisonnier | 3 430-3 493 | 6,4-7,1 % | 0,98-1,00 | 0,70-0,88 |

- **Les covariables comptent plus que le modèle** : Chronos-2 passe de 1 752 à 1 109 MW quand on lui donne la
  météo et le calendrier. Zero-shot sans covariables, un TSFM ne sait pas qu'il va faire froid demain.
- **MSTL et ETS ne font pas mieux que la naïve d'un facteur 2.** Sans météo, un modèle univarié ne peut pas suivre
  un hiver.
- **Le mélange bat ses deux membres.** LightGBM et Chronos-2 se trompent à des moments différents ; la moyenne des
  quantiles réduit le MAE de 8 % par rapport au meilleur des deux.

## Le portefeuille FlexGrid

(Section complétée quand le backtest du panel est terminé.)
