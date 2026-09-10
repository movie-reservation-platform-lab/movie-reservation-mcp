# Movie Reservation MCP

MCP wrapper for the movie reservation GraphQL API.

This repository exists so the reservation MCP can have its own issue tracker,
CI, and artifact pipeline while the implementation is extracted from the
golden-path/demo baseline.

## Run

```sh
uv run movie-reservation-mcp
```

The production container runs as UID `10001` and listens on port `8091`:

```sh
docker build --tag movie-reservation-mcp:local .
docker run --rm --network host movie-reservation-mcp:local
```

The demo assumes the MCP and reservation API containers share one ECS task
network namespace, so the default downstream address remains
`127.0.0.1:3000`. Override the downstream URLs when running the containers
independently.

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
uv run --frozen --no-sync pytest tests
uv run --frozen --no-sync pytest automation/tests
uv run --frozen --no-sync ruff check .
uv run --frozen --no-sync ruff format --check .
uv run --frozen --no-sync python -m compileall src tests automation
```

Pushes to `main` publish a Linux AMD64 candidate to GHCR as
`sha-<commit>-run-<run-id>-attempt-<attempt>`. CI disables BuildKit's automatic registry attestation to keep
the candidate a single-image manifest, then records explicit GitHub build
provenance against the published digest for the environment admission gate.

### Container security evidence

The pinned organization-owned actions publish the signed
`reservation-mcp-security-evidence-<run-id>-attempt-<attempt>` artifact:
`component-candidate-evidence-v1alpha2.json`, verified image provenance,
CycloneDX SBOM, and subject-bound vulnerability report. Evidence is retained
for 14 days. Missing provenance or CRITICAL findings fail publication of the
canonical evidence package; HIGH findings remain visible for admission review.

Run/attempt tags are discovery hints, not deployment selectors. Environment
verification independently checks the successful canonical run and signed
package before admitting its exact digest to ECR. This producer has no AWS
credentials or deployment authority. Older runs without this package are not
eligible for the new admission path; use a fresh successful main run.
See [the shared action contract](https://github.com/movie-reservation-platform-lab/movie-platform-actions/blob/9b7b5a601367a45356687a0e1bf1d1638d62aca9/docs/container-candidate-actions.md).
