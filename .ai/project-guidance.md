# Project AI Guidance

This repository owns the Python FastMCP wrapper around the reservation GraphQL
API. It exposes stable reservation tools to `movie-reservation-agent` and keeps
transport, downstream GraphQL, and observability propagation at the adapter
boundary.

## Repository Layout

- `src/movie_reservation_mcp/server.py`: FastMCP tools, health route, and
  process entry point.
- `src/movie_reservation_mcp/reservation_client.py`: downstream GraphQL adapter,
  configuration, metadata propagation, and response handling.
- `tests/`: tool-contract, client, error, and propagation coverage.
- `.ai/`: canonical AI guidance, skills, and read-only review agents.

## Development Commands

- Install/sync: `uv sync --frozen`
- Tests: `uv run --frozen --no-sync pytest`
- Lint: `uv run --frozen --no-sync ruff check .`
- Format check: `uv run --frozen --no-sync ruff format --check .`
- Compile check: `uv run --frozen --no-sync python -m compileall src tests`

Inspect `pyproject.toml` and the workflow before changing or inventing commands.

## Tool And Adapter Contracts

- Keep these tool names stable unless coordinating an agent migration:
  `reservation_get_catalog`, `reservation_request_seats`,
  `reservation_get_request_status`, and `reservation_health`.
- Keep MCP tools thin: validate tool input, construct metadata, call the client,
  and map a stable tool result.
- Keep GraphQL documents, endpoint configuration, HTTP lifecycle, timeout, and
  response parsing in the downstream client adapter.
- Preserve `traceparent`, `tracestate`, `X-Correlation-Id`, `X-Request-Id`, and
  `X-Demo-Fault` without accepting arbitrary forwarded headers.
- Return bounded, safe errors. Do not leak downstream bodies, tokens, URLs with
  credentials, or stack traces through tool results.
- Health and readiness behavior must remain useful to local orchestration and
  ECS without making normal tool calls depend on a global mutable health state.

## Repository Boundaries

- The reservation API owns reservation behavior and persistence.
- The agent owns orchestration and user-facing dialogue behavior.
- This repository owns only the MCP translation and downstream adapter.
- Publish an immutable container image; environment selection and deployment
  belong to the platform repositories.

## Testing Guidance

- Test tool names, input validation, payload mapping, downstream errors,
  timeout behavior, and propagated metadata.
- Use `httpx.MockTransport` or a narrow fake client instead of real network I/O
  in ordinary tests.
- Keep smoke coverage for the real MCP-to-GraphQL boundary separate and
  explicitly configured.

## Safety

- Do not commit secrets, credentials, tokens, local env values, or production
  payloads.
- Treat configurable downstream URLs, propagated metadata, GraphQL errors, and
  mutating tools as security-sensitive boundaries.
- Do not push, deploy, promote, or mutate AWS/shared environment state without
  explicit user instruction.

## Planning And Review

- Use `principal-engineer-planner` before tool-contract, transport, topology,
  observability, or compatibility changes.
- Save implementation plans under `docs/plans/`.
- Ask review agents for findings first and require file/line evidence.
