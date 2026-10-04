.PHONY: test lint data build figures tables report all

QUARTO_PYTHON ?= $(CURDIR)/.venv/bin/python
export QUARTO_PYTHON

test:
	uv run pytest

lint:
	uv run ruff check src tests && uv run ruff format --check src tests

data:
	uv run flexgrid download

build: data
	uv run flexgrid build

tables:
	uv run flexgrid tables

figures:
	uv run flexgrid figures-data
	uv run flexgrid figures-results
	uv run flexgrid figures-router
	uv run python -m flexgrid.figures_monitoring
	uv run python -m flexgrid.figures_design

report:
	report/prepare.sh
	cd report && quarto render

all: tables figures report
