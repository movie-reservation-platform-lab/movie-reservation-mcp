# Implementation Plan: Trace-connected reservation MCP telemetry

## 1. Summary

Add native OpenTelemetry spans, metrics, and correlated JSON stdout logs around
the four existing MCP tools. Extract W3C context from the existing tool
arguments before opening each server span, and let HTTPX instrumentation inject
the active child context into reservation API calls. Preserve all public tool,
health, and safe-error contracts.

## 2. Goals

- Join an incoming distributed trace and connect the downstream HTTP span.
- Report success, validation failure, and dependency failure truthfully.
- Emit bounded tool call and duration metrics with observed local payload proof.
- Emit correlated structured logs without sensitive or unbounded metric labels.
- Remain usable when no exporter or collector is configured.

## 3. Non-goals

- Collector/CDK wiring, backend queries, dashboards, deployment, or publication.
- Changes to tool names, arguments, results, fault behavior, or API behavior.
- HTTP server metrics for FastMCP transport or the `/health` route.
- DORA telemetry or a general-purpose shared telemetry package.

## 4. Current State

`server.py` exposes four stable tools and maps validation and
`ReservationClientError` failures into safe dictionaries. `reservation_client.py`
forwards an allowlisted metadata carrier, but no SDK extracts it into the active
context and no native metrics, spans, or structured events are emitted. The
client uses one `httpx.AsyncClient`; the repository has no direct OpenTelemetry
runtime dependencies or exporter evidence tests.

## 5. Requirements and Assumptions

### Confirmed Requirements

- Follow the advisory signal contract in `movie-platform-infra#57`.
- Use canonical resource attributes: `service.name`, `service.namespace`,
  `deployment.environment.name`, and `service.version`.
- Keep metric dimensions limited to allowlisted tool name and bounded outcome.
- Use the future task-local OTLP/HTTP collector endpoint; infra currently plans
  port 4322.
- Telemetry loss must not fail requests.

### Assumptions

- Existing `traceparent` and `tracestate` tool arguments remain the incoming
  carrier until FastMCP supplies a framework-level extraction hook.
- OpenTelemetry's standard OTLP environment variables configure exporter paths,
  timeout, and headers; application code supplies no secrets.
- Health route traffic is excluded from tool health metrics.

### Open Questions

- The final AMP-translated series names and collector acceptance remain owned by
  infra #57. This PR records the native payload shape and expected Prometheus
  translation without claiming backend acceptance.

## 6. Proposed Design

Add a small `telemetry.py` adapter that configures SDK resources/exporters,
HTTPX instrumentation, JSON logging, and a `tool_call` context manager. A tool
call extracts W3C context first, creates a `SERVER` span, records exactly one
call count and duration with a finite outcome, marks failure spans as errors,
and emits start/completion events with active trace identifiers.

Tool functions retain validation and downstream mapping, but explicitly finish
their observation with `success`, `validation_error`, or `dependency_error`.
The HTTPX instrumentation creates a client child span and injects the active
context. Raw trace headers, IDs, and fault values never become metric labels.

## 7. Alternatives Considered

### Alternative A: Copy recommendation MCP telemetry

- Pros: small initial diff.
- Cons: records returned dependency failures as success, does not extract the
  incoming carrier, and uses caller-controlled fault values as metric labels.
- Decision: rejected because these are the defects issue #6 must avoid.

### Alternative B: Manual downstream spans and propagation

- Pros: deterministic and dependency-light.
- Cons: duplicates established HTTP semantic conventions and can drift from
  actual HTTPX behavior.
- Decision: rejected in favor of standard HTTPX instrumentation plus focused
  parentage tests.

## 8. API / Interface Changes

No public tool or result changes. Runtime gains standard `OTEL_*` configuration
and optional `SERVICE_NAMESPACE`, `SERVICE_VERSION`, and
`DEPLOYMENT_ENVIRONMENT` resource configuration.

Native metrics:

- `movie_reservation_mcp_tool_calls` counter, unit `{call}`.
- `movie_reservation_mcp_tool_duration` histogram, unit `s`.
- Attributes: `mcp.tool.name` and `outcome` only.

## 9. Data Model / Persistence Changes

None.

## 10. Security, Privacy, and Abuse Considerations

Only existing allowlisted propagation fields are accepted. Correlation and
request IDs are length-bounded before logs/spans. Trace IDs come from validated
OpenTelemetry context. No request bodies, seat IDs, GraphQL payloads, exception
messages, credentials, raw URLs, or fault values are emitted as metric labels.

## 11. Performance, Scalability, and Reliability Considerations

Batch span export and periodic metric export keep network work off the request
path. Exporter queues/timeouts use SDK bounds. Missing configuration installs
local providers without exporters, preserving context and application behavior.
Metrics use two fixed dimensions and four fixed tool names.

## 12. Implementation Steps

1. Add direct OpenTelemetry dependencies and telemetry adapter.
   - Files: `pyproject.toml`, `uv.lock`, `src/movie_reservation_mcp/telemetry.py`.
   - Verification: configuration/resource tests and frozen dependency sync.
2. Instrument tool outcomes and downstream HTTPX calls.
   - Files: `server.py`, minimally `reservation_client.py` if client-level
     instrumentation ownership requires it.
   - Verification: success, validation, GraphQL, transport, and no-exporter tests.
3. Capture local emitted evidence and document exact mappings.
   - Files: `tests/test_telemetry.py`, `docs/observability/local-signal-evidence.md`,
     `README.md`.
   - Verification: in-memory spans/metrics prove incoming parent, HTTP child,
     finite attributes, real outcomes, identity, and zero/idle behavior.
4. Run the repository's complete frozen checks and container smoke.

## 13. Testing Strategy

- Unit-test carrier extraction, field bounding, JSON envelope, and provider setup.
- Use in-memory span and metric exporters for exact native evidence.
- Instrument a mock-transport HTTPX client to prove downstream parentage and
  replacement of the raw incoming carrier with the active context.
- Exercise stable server results for success, validation failure, GraphQL
  business error, and transport failure.
- Verify no exporter configuration preserves tool behavior.
- Run full pytest, Ruff lint/format, compile, diff check, and container smoke.

## 14. Rollout / Migration Plan

Publish an immutable image only after review. Infra #57 then adds the dedicated
loopback receiver and accepts the recorded payload. Environment composition
selects all compatible digests together. Rollback restores the prior full
composition; telemetry absence must not alter application requests.

## 15. Risks and Mitigations

| Risk | Impact | Likelihood | Mitigation |
| --- | ---: | ---: | --- |
| Returned failures appear successful | High | Medium | Require explicit finite outcome before each return and test every branch. |
| Raw incoming carrier reaches downstream unchanged | High | Medium | Assert HTTP span parentage and injected child span ID. |
| Global SDK setup makes tests flaky | Medium | Medium | Keep the adapter injectable and test with local providers/readers. |
| Metric labels grow without bound | High | Low | Central allowlists and negative attribute assertions. |
| Export outage affects tools | High | Low | Batch/periodic exporters, no synchronous flush on calls, no-exporter test. |

## 16. Done Criteria

- Incoming parent, MCP server span, and downstream HTTP span form one trace.
- Metrics distinguish success, validation, and dependency outcomes with finite
  labels and measured seconds.
- JSON events contain canonical identity and active trace IDs without secrets.
- Existing tools, results, health, and allowlisted metadata remain compatible.
- Local evidence documents actual SDK payloads and unresolved infra translation.
- All frozen checks and container smoke pass.

## 17. Review Checklist

- [x] Requirements and non-goals are explicit.
- [x] Existing tool/client conventions were checked.
- [x] Alternatives were considered.
- [x] Security, reliability, tests, rollout, and rollback are covered.
- [x] Steps name affected files and verification.

## 18. Handoff Prompt for Implementation Agent

```text
Implement docs/plans/trace-connected-otel-telemetry.md for issue #6.
Preserve the stable tool/result contracts. Use extracted W3C context, bounded
tool/outcome metrics, safe correlated logs, and standard HTTPX instrumentation.
Capture exact local exporter evidence and run the full frozen repository checks.
Do not change infra, publish an image, or deploy.
```
