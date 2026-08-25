# syntax=docker/dockerfile:1.7

ARG PYTHON_IMAGE=python:3.12-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.12.3

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS base

COPY --from=uv /uv /uvx /bin/

ENV FASTMCP_CHECK_FOR_UPDATES=off \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PYTHON_PREFERENCE=only-system \
    UV_PROJECT_ENVIRONMENT=/venv \
    VIRTUAL_ENV=/venv \
    PATH=/venv/bin:$PATH

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl tini \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

FROM base AS dependencies
COPY .python-version pyproject.toml README.md uv.lock /app/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project --no-dev --frozen

FROM dependencies AS build
COPY src /app/src
RUN uv sync --no-dev --compile-bytecode --no-editable --frozen

FROM base AS prod
COPY --from=build /venv /venv
COPY --from=build /app /app

RUN useradd -r -u 10001 appuser && chown -R appuser:appuser /app /venv
USER appuser

EXPOSE 8091
HEALTHCHECK --interval=30s --timeout=3s --retries=3 CMD \
  sh -c 'curl -fsS http://127.0.0.1:8091/health || exit 1'

ENTRYPOINT ["/usr/bin/tini","--"]
CMD ["movie-reservation-mcp"]
