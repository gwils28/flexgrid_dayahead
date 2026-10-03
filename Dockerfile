# Image du service J-1 : code, dépendances figées par uv.lock. Les données (snapshots, magasin, registre)
# sont montées en volume, jamais copiées dans l'image ; le token ENTSO-E arrive par un secret Docker.
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8.15 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy DAGSTER_HOME=/app/dagster_home

COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --extra prod --no-dev --no-install-project
COPY src ./src
COPY configs ./configs
RUN uv sync --frozen --extra prod --no-dev

EXPOSE 8000 3000
CMD ["uv", "run", "--no-sync", "uvicorn", "flexgrid.prod.api:app", "--host", "0.0.0.0", "--port", "8000"]
