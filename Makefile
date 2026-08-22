.PHONY: test lint data build figures all

test:
	uv run pytest

lint:
	uv run ruff check src tests && uv run ruff format --check src tests

data:
	uv run flexgrid download

build: data
	uv run flexgrid build

figures:
	uv run flexgrid figures-data

all: build figures
