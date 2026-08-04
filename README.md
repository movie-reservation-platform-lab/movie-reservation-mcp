# Movie Reservation MCP

MCP wrapper for the movie reservation GraphQL API.

This repository exists so the reservation MCP can have its own issue tracker,
CI, and artifact pipeline while the implementation is extracted from the
golden-path/demo baseline.

## Current State

This is a scaffold. The first implementation issue should port or rebuild the
reservation MCP tool contract proven by the local multi-service observability
demo:

```text
browser -> Python agent -> recommendation MCP -> Rust recommendation API
                        -> reservation MCP -> NestJS reservation API
```

## Expected Runtime Contract

- MCP endpoint: `http://127.0.0.1:8091/mcp`
- Health endpoint: `http://127.0.0.1:8091/health`
- Downstream API: configured by `MOVIE_RESERVATION_GRAPHQL_URL`

Expected tools:

- `reservation_get_catalog`
- `reservation_request_seats`
- `reservation_get_request_status`
- `reservation_health`

Tools should forward:

- `traceparent`
- `tracestate`
- `X-Correlation-Id`
- `X-Request-Id`
- `X-Demo-Fault`

## Checks

```sh
python -m compileall src
```
