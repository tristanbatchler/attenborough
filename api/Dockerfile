# The API. Built and run by ../docker-compose.yml; see ../deploy/README.md.

FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim AS build

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

# Dependencies first, so that a code change doesn't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-editable --no-install-project
COPY src ./src
# Installed, not editable: the package runs from the virtual environment, without its source tree,
# so the app knows it isn't a source checkout (settings.SOURCE_CHECKOUT) and writes no files.
RUN uv sync --frozen --no-dev --no-editable


FROM python:3.14-slim-bookworm

WORKDIR /app
COPY --from=build /app/.venv ./.venv
# The scripts a deployment runs: `docker compose run --rm migrate`, and the latency check.
COPY scripts/migrate.py scripts/exhibit_latency.py ./scripts/
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# No user account needed: an unprivileged uid that owns nothing on the host.
USER 10001:10001
EXPOSE 8000
# Reachable only on its internal networks (docker-compose.yml). FORWARDED_ALLOW_IPS comes from the
# environment, so uvicorn's own proxy-header layer and the app's agree.
CMD ["uvicorn", "attenborough.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header"]
