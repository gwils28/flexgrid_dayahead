**Cas d'usage client (énergie · projet 1–2 mois)** — brief d'origine, conservé tel quel. Les décisions prises
avant d'écrire du code sont dans [`SPEC.md`](SPEC.md), les écarts dans [`IMPLEMENTATION_NOTES.md`](IMPLEMENTATION_NOTES.md).

Il applique la veille [W25 — quand un TSFM zero-shot bat-il un spécialiste réajusté ?](https://github.com/gwils28/W25_tsfm_viability).

---

### Contexte & problématique

**Client fictif : « FlexGrid Énergie »**, agrégateur de flexibilité et **Responsable d'Équilibre (BRP)** français gérant un portefeuille d'environ 5 000 sites tertiaires + un parc de bornes de recharge, soit ~800 GWh/an. Chaque jour, FlexGrid doit **nommer J-1** la consommation agrégée de son portefeuille au pas 30 min pour optimiser ses achats sur le marché day-ahead et minimiser son exposition au **tarif de règlement des écarts** (imbalance). Aujourd'hui, leur prévision J-1 plafonne à ~6 % de MAPE ; or chaque point de MAPE se paie en énergie d'équilibrage achetée au prix fort. *Ordre de grandeur illustratif :* sur un tel portefeuille, réduire le MAPE de 6 % à 4 % peut représenter plusieurs centaines de k€/an de pénalités évitées. Les séries temporelles sont la réponse naturelle : forte saisonnalité multiple (intra-journalière, hebdomadaire, annuelle), forte dépendance météo, et un benchmark public à battre (la prévision J-1 de RTE).

### Sources de données (réelles, vérifiées)

1. **ODRÉ — éCO2mix national consolidé & définitif (janv. 2012 → janv. 2026)** → https://odre.opendatasoft.com/explore/dataset/eco2mix-national-cons-def/
Données consolidées et définitives au pas demi-heure pour la consommation réalisée, et au pas quart d'heure pour les prévisions de consommation établies la veille (J-1) et réactualisées le jour même. → **La prévision J-1 incluse est ta baseline à battre.** Granularité 15/30 min ; horizon J-1 (24–36 h).
2. **ENTSO-E Transparency Platform** → https://transparency.entsoe.eu/
Accès libre et continu aux données de marché électrique pan-européennes : Load, Generation, Balancing, Market…. Tu y récupères l'**Actual Total Load (6.1.A)**, le **Day-ahead Total Load Forecast (6.1.B)** et les **prix day-ahead** — indispensables pour modéliser le coût d'écart, pas seulement le volume.
3. **Open Power System Data — Time series package** → https://data.open-power-system-data.org/time_series/
Consommation électrique (load) pour 37 pays européens, plus génération éolienne/solaire et prix, en résolution horaire, fusionnés en CSV propre. Idéal pour le **bloc code du jour** et pour des séries de transfert (cold-start) au-delà de la France.

*Covariable exogène recommandée :* températures quotidiennes par département (ODRÉ / data.gouv) pour dériver HDD/CDD — la météo explique l'essentiel de la variance de charge.

### Cahier des charges technique

**A. Préparation des données**

- Alignement multi-sources (15 min ↔ 60 min), gestion explicite des **transitions heure d'été/hiver** (l'heure dupliquée d'octobre est le bug classique des données de charge).
- Imputation : interpolation linéaire sur trous ≤ 2 h, traitement explicite des trous longs (pas de fill silencieux).
- Calendrier FR : jours fériés (`jours-feries-france`), ponts, vacances scolaires, effet jour-de-semaine.
- Exogènes : HDD/CDD à partir des températures, lags météo, normalisation par RevIN/standardisation par série.

**B. Approche de modélisation (baseline → avancé)**

- **Baseline** : `SeasonalNaive` + `MSTL`/`AutoETS` (saisonnalités 48 et 336 pas).
- **Avancé 1 (supervisé)** : gradient boosting (LightGBM) sur lags + calendrier + météo → fort sur les contraintes connues.
- **Avancé 2 (TSFM)** : Chronos-2 ou TTM-r3 / PatchTST-FM en zero-shot, puis few-shot in-context sur les sites cold-start.
- **Routage** : *Complexity Router* arbitrant par site/segment entre spécialiste et TSFM (cf. Livrable 1, bloc 3).
- **Sortie probabiliste obligatoire** : quantiles (pinball loss) — le bidding se fait sous incertitude, pas sur un point.

**C. Backtesting & évaluation**

- Rolling-origin / fenêtre glissante sur **≥ 12 mois**, cadence de refit définie (hebdo).
- Métriques : **MASE**, **sMAPE**, **WAPE**, **pinball loss / CRPS**, **couverture @ 90 %**.
- **Benchmark imposé** : battre la prévision J-1 de RTE/éCO2mix ; sinon, le projet n'a pas de valeur démontrable.
- Métrique métier : traduire l'erreur en **€ d'écart d'équilibre** (volume × prix), pas seulement en %.

**D. Stack de mise en production**

- Orchestration J-1 : Airflow / Dagster (ingestion API ENTSO-E + éCO2mix → features → forecast → nomination).
- Feature store + model registry (MLflow), versioning des données (DOI OPSD / snapshots).
- Serving batch J-1 + API quantiles ; conteneurisation ; secrets pour le token API ENTSO-E.

**E. Stratégie de monitoring**

- **Data drift** : PSI / KS sur load, météo, prix.
- **Concept drift** : MASE/CRPS glissant vs baseline RTE ; alerte si dégradation persistante → retraining.
- **Calibration** : suivi de la couverture réelle des intervalles (un 90 % qui dérive à 70 % = perte d'argent).
- **Décision de routage** : distribution des routes et taux de bascule dans le temps.
- **KPI métier** : coût d'écart mensuel piloté comme métrique de tête.
