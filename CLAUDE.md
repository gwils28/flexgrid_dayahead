# FlexGrid day-ahead

## Commandes
- `uv sync` (ajouter `--extra prod` pour Dagster, MLflow, FastAPI) puis `uv run pytest` (tests rapides ;
  `-m slow` lit les données téléchargées et les poids Chronos-2).
- `uv run ruff check src tests && uv run ruff format src tests`.
- `make data` télécharge et fige les sources ; `make all` reproduit tableaux, figures et rapport.
- Quarto : `QUARTO_PYTHON=.venv/bin/python`.

## Pièges
- `data/raw/` est figé : chaque fichier a son sha256 dans `data/MANIFEST.json`. Ne jamais le modifier ; un
  nouveau téléchargement porte un nouveau nom.
- `configs/protocol.yaml` est pré-enregistré. Un changement après avoir vu des résultats est une déviation :
  commentaire daté, valeur d'origine conservée, entrée dans `IMPLEMENTATION_NOTES.md`.
- Tout est en UTC ; jours de livraison, calendrier et heure d'émission en heure de Paris. Un jour local a
  46, 48 ou 50 pas.
- éCO2mix publie des lignes fantômes en mars (heure locale inexistante) : `national.drop_phantom_rows`.
- Aucune entrée d'un modèle ne doit dépasser l'horloge de nomination (`clock` du protocole) : conso nationale
  jusqu'à J-1 08:00, segments jusqu'à la fin de J-2, météo `previous_day2`.
- La météo observée (ERA5) ne sert jamais au verdict, seulement à l'apprentissage et à l'ablation.
- Chronos-2 en `cross_learning` : un lot ne contient que des séries coupées au même instant.
- utilsforecast `smape` vaut la moitié du sMAPE de manuel ; nos tableaux donnent celui du manuel.

## Conventions
- Un nombre écrit dans un README ou le rapport vient de `results/` ou d'une commande montrée à côté.
- Figures : palette `flexgrid.plots`, une couleur par modèle, chaque figure regardée après rendu.
- Docstrings, README et rapport en français ; identifiants en anglais.

## Compaction
Garder : fichiers modifiés, commandes de test, liste des déviations, chaque décision de modélisation avec sa
raison, l'état du calendrier de commits.

Canari : finir chaque résumé final par la ligne « FlexGrid ok ».
