---
name: python-mcp-service
description: Use when implementing, refactoring, reviewing, or explaining Python FastMCP services, including tool definitions, tool input/result contracts, downstream httpx clients, health routes, configuration, lifecycle, safe errors, and trace/correlation propagation.
---

# Python MCP Service

Use this skill for the adapter boundary between an agent and a downstream movie
platform API.

## Tool Contracts

- Treat tool names and input/result shapes as consumer-facing APIs.
- Prefer additive evolution; coordinate renames or required-field changes with
  `movie-reservation-agent`.
- Keep decorated tool functions thin and typed.
- Validate identifiers, non-empty collections, ranges, and bounded strings
  before downstream I/O.
- Return a consistent success/error envelope that is useful to the agent but
  does not expose internal exceptions or raw provider payloads.
- Separate demo fault controls from ordinary business inputs.

## Downstream Client Boundary

- Keep endpoints, timeouts, auth/config, HTTP lifecycle, request construction,
  response parsing, and downstream error classification in a client adapter.
- Use one managed `httpx.AsyncClient` per service lifecycle where practical;
  close owned clients during shutdown.
- Apply finite timeouts and classify timeout, connection, protocol, non-success,
  and malformed-payload failures.
- Do not retry mutating operations unless idempotency is explicit.
- Validate configured URLs and avoid forwarding caller-controlled arbitrary
  headers.

## Observability

- Propagate only the platform contract: W3C trace context, correlation ID,
  request ID, and controlled demo-fault metadata.
- Keep IDs out of metric labels.
- Log safe operation names, outcomes, durations, and correlation fields; do not
  log tokens or full sensitive payloads.
- Keep delivery/DORA telemetry outside this runtime adapter.

## FastMCP And Health

- Keep FastMCP decorators, transport setup, and Starlette routes at the outer
  edge.
- Keep `/health` and readiness behavior bounded and deterministic.
- Distinguish service liveness from downstream dependency health when the
  deployment contract needs both.
- Keep process startup free of hidden network calls unless readiness explicitly
  owns that check.

## Workflow

1. Inspect the existing tool and downstream API contracts.
2. Identify compatibility and failure semantics before editing.
3. Change the smallest tool/client boundary.
4. Add contract tests for success, invalid input, downstream failure, timeout,
   malformed response, and metadata propagation as applicable.
5. Run frozen pytest, Ruff lint/format, and compile checks from the repository
   root.
