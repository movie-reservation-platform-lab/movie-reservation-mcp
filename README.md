# Movie Reservation MCP

MCP wrapper for the movie reservation GraphQL API.

This repository exists so the reservation MCP can have its own issue tracker,
CI, and artifact pipeline while the implementation is extracted from the
golden-path/demo baseline.

## Run

```sh
uv run movie-reservation-mcp
```

Defaults:

- MCP endpoint: `http://127.0.0.1:8091/mcp`
- Health endpoint: `http://127.0.0.1:8091/health`
- Downstream GraphQL API: `http://127.0.0.1:3000/graphql`
- Downstream health API: derived as `http://127.0.0.1:3000/health`

```text
browser -> Python agent -> recommendation MCP -> Rust recommendation API
                        -> reservation MCP -> NestJS reservation API
```

Useful environment variables:

- `MOVIE_RESERVATION_GRAPHQL_URL`
- `MOVIE_RESERVATION_HEALTH_URL`
- `MOVIE_RESERVATION_API_TIMEOUT_SECONDS`
- `PORT`
- `HOST`

## Tools

- `reservation_get_catalog`
  - Inputs: optional `movie_id`, optional `fault`, and optional propagation fields.
  - Calls GraphQL `movies` and `screenings(movieId)`.
- `reservation_request_seats`
  - Inputs: `screening_id`, `seat_ids`, optional `fault`, and optional propagation fields.
  - Calls GraphQL `requestReservation(input)`.
- `reservation_get_request_status`
  - Inputs: `reservation_request_id`, optional `fault`, and optional propagation fields.
  - Calls GraphQL `reservationRequestStatus(id)` and `reservationResult(requestId)`.
- `reservation_health`
  - Calls downstream `GET /health`.

Tools forward:

- `traceparent`
- `tracestate`
- `X-Correlation-Id`
- `X-Request-Id`
- `X-Demo-Fault`

## Checks

```sh
uv sync --frozen
uv run --frozen --no-sync pytest
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync ruff format --check .
uv run --frozen --no-sync python -m compileall src tests
```
