#!/usr/bin/env bash
# Prépare le rapport : copie les figures des blocs et réécrit les liens des README pour le site.
# Les README restent la source unique ; report/_inc/ et report/figures/ sont générés (ignorés par git).
set -euo pipefail
cd "$(dirname "$0")/.."
GH=https://github.com/gwils28/flexgrid_dayahead/blob/main
rm -rf report/_inc report/figures && mkdir -p report/_inc report/figures
for b in 01_donnees 02_backtest 03_router 04_cout 05_production; do
  cp "$b"/figures/*.png report/figures/
  # ../0X_bloc/README.md -> page du site ; ../autre -> fichier sur GitHub
  sed -E -e "1{/^# /d}" -e "s#\]\(\.\./(0[1-5]_[a-z_]+)/README\.md#](\1.qmd#g" -e "s#\]\(\.\./#](${GH}/#g" \
    "$b/README.md" > "report/_inc/$b.md"
done
sed -E -e "1{/^# /d}" -e "s#\]\((0[1-5]_[a-z_]+)/README\.md#](\1.qmd#g" -e "s#\]\((0[1-5]_[a-z_]+)/figures/#](figures/#g" \
  -e "s#\]\(([A-Za-z_]+\.md|configs/[a-z_.]+)\)#](${GH}/\1)#g" README.md > report/_inc/README.md
