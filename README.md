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

The optional development target keeps `uv`, curl, source, and test tooling in a
separate image:

```sh
docker build --target development --tag movie-reservation-mcp:development .
docker run --rm --network host movie-reservation-mcp:development
```

Production starts from the clean Python runtime stage, copies only the installed
virtual environment, and uses Python for its health check. Build and development
tools remain in their own stages.

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
`component-candidate-evidence-v1alpha3.json`, verified image provenance,
CycloneDX SBOM, and subject-bound vulnerability report. Evidence is retained
for 14 days. Missing provenance or any CRITICAL finding without a current,
exact central exemption fails publication of the canonical evidence package.
Raw findings stay visible; covered findings produce `passed-with-exemptions`.
HIGH findings remain visible for admission review.

Run/attempt tags are discovery hints, not deployment selectors. Environment
verification independently checks the successful canonical run and signed
package before admitting its exact digest to ECR. This producer has no AWS
credentials or deployment authority. Older runs without this package are not
eligible for the new admission path; use a fresh successful main run.
The environment reader must support v1alpha3 before admission. It independently
reevaluates original findings against the latest approved central policy.
See [the shared action contract](https://github.com/movie-reservation-platform-lab/movie-platform-actions/blob/036531133bcefd454b5afc0eb55f8ba0328901ea/docs/container-candidate-actions.md).

This producer adopts [actions PR #18](https://github.com/movie-reservation-platform-lab/movie-platform-actions/pull/18)
at `036531133bcefd454b5afc0eb55f8ba0328901ea`, following the validated
[recommendation-MCP canary PR #13](https://github.com/movie-reservation-platform-lab/movie-recommendation-mcp/pull/13).
Both publisher actions and the PR/local scanner use that reviewed revision.
Prepare receives `github-token: ${{ github.token }}` for its authenticated
canonical-main lookup, using the publishing job's existing `contents: read`
permission. Its other publishing permissions remain necessary; passing the token
does not reduce its authority. The release also hardens evidence failure paths,
including bounded legacy report reads and sanitized failures, and scanner cleanup.
Evidence remains v1alpha3 for `reservation-mcp`.

Offline caller tests verify wiring, permissions and event guards. Hosted PR scanning
does not exercise prepare or prove private-repository access or canonical publication;
those require separate post-merge acceptance. Publication remains restricted to a push
on this repository's canonical main. Rollback reverts both publisher pins, the PR/local
tooling checkout, and the documented local tooling pin to
`bb40579c285df0b581c48b10f9b34574d5c78639`, and removes the prepare token input
together. See the [adoption plan](docs/plans/authenticated-prepare-adoption.md).

### PR and local vulnerability checks

`container-security-check` builds the production linux/amd64 image on PRs and
other non-canonical runs. It uses the same reviewed shared tooling and v1alpha3
policy as publication, with only `contents: read`. The GitHub token is supplied
only to the scan/evaluation step to read approved policy from the actions repo.
An uncovered CRITICAL or a scanner/policy retrieval error fails the job.

The complete report, policy decisions and summary are retained for 14 days as
`reservation-mcp-pr-vulnerability-report-<run>-attempt-<attempt>`, including
after a failed gate. These local-image diagnostics are not signed candidate
evidence. Canonical main publication independently scans its exact GHCR digest.

To reproduce using a sibling actions checkout at the reviewed commit:

```sh
git -C ../movie-platform-actions rev-parse HEAD
# Expected: 036531133bcefd454b5afc0eb55f8ba0328901ea
docker build --pull --platform linux/amd64 --target prod \
  --tag movie-reservation-mcp:local .
# Supply GH_TOKEN securely through your normal environment setup.
node ../movie-platform-actions/local-tools/container-security/lib/scan.mjs \
  movie-reservation-mcp:local \
  --evidence-version v1alpha3 --component reservation-mcp
```

The helper writes an ignored `.local-container-security/run-*/` directory.
Exit 0 means policy pass, 1 means blocking findings, and 2 means an operational
or validation failure. The report includes all severities and unfixed findings;
HIGH findings remain visible but do not block under the current central policy.
This change requests no exemptions. Scanner and policy failures retain available
diagnostics and never count as a successful security check.
