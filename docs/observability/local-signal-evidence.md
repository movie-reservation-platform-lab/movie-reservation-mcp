# Reservation MCP local signal evidence

Tracking: [issue #6](https://github.com/movie-reservation-platform-lab/movie-reservation-mcp/issues/6)
and [infra issue #57](https://github.com/movie-reservation-platform-lab/movie-platform-infra/issues/57).

## Evidence boundary

This records payloads observed through OpenTelemetry SDK in-memory exporters in
`tests/test_telemetry.py`. It proves producer emission before publication or
collector/backend integration. It does not claim acceptance by ADOT, AMP,
CloudWatch, X-Ray, or Tempo.

Run the evidence tests with:

```sh
uv run --frozen --no-sync pytest tests/test_telemetry.py -q
```

## Resource identity

Both spans and metrics carry:

| Resource attribute | Observed test value | Runtime source |
| --- | --- | --- |
| `service.name` | `movie-reservation-mcp` | `OTEL_SERVICE_NAME` |
| `service.namespace` | `movie-platform` | `SERVICE_NAMESPACE` |
| `service.version` | `test-version` | `SERVICE_VERSION` |
| `deployment.environment.name` | `test` | `DEPLOYMENT_ENVIRONMENT` |

Runtime defaults are documented in the README. Deployment owns the production
values.

## Native metrics

| Name | SDK type | Unit | Attributes | Observed outcomes |
| --- | --- | --- | --- | --- |
| `movie_reservation_mcp_tool_calls` | monotonic counter | `{call}` | `mcp.tool.name`, `outcome` | `success`, `validation_error`, `dependency_error` |
| `movie_reservation_mcp_tool_duration` | histogram | `s` | `mcp.tool.name`, `outcome` | same finite set |

`internal_error` is reserved for an unexpected exception escaping tool logic.
The fixed tool-name allowlist is `reservation_get_catalog`,
`reservation_request_seats`, `reservation_get_request_status`, and
`reservation_health`.

The success fixture emitted this exact counter point:

```json
{
  "name": "movie_reservation_mcp_tool_calls",
  "unit": "{call}",
  "value": 1,
  "attributes": {
    "mcp.tool.name": "reservation_get_catalog",
    "outcome": "success"
  }
}
```

The failure fixtures emitted `validation_error` for rejected tool input and
`dependency_error` for both a GraphQL error carried by HTTP 200 and an HTTPX
transport timeout. Tests assert that correlation IDs, request IDs, fault text,
seat IDs, exception messages, and downstream bodies are absent from metric
attributes.

The SDK exports cumulative counter and histogram points. Before the first tool
call, no point exists. Idle periods do not invent calls, error zeros, or
zero-duration observations. Collector/backend freshness must therefore remain a
separate guard; missing or stale series cannot be interpreted as healthy zero.
The planned Prometheus counter translation is
`movie_reservation_mcp_tool_calls_total`, subject to infra #57 collector proof.

## Traces and propagation

The deterministic propagation fixture uses remote parent:

```text
trace ID: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
remote span ID: bbbbbbbbbbbbbbbb
```

Observed topology:

```text
remote caller span
└── SERVER mcp.tool.reservation_get_catalog
    └── CLIENT POST
```

The MCP span retains the remote trace ID and parent span ID. The downstream
request uses the same trace ID but injects the HTTP client span ID, proving that
the raw incoming `traceparent` is not merely replayed. `tracestate` is preserved.
Validation, GraphQL, and transport failures mark the MCP span as error; returned
safe tool envelopes remain unchanged.

## Structured stdout

The JSON formatter emits timestamp, severity, canonical service name/version,
event, and message. Active calls add trace/span IDs; bounded real inputs may add
correlation/request IDs. A representative completion shape is:

```json
{
  "event": "mcp.tool.completed",
  "message": "Reservation MCP tool completed.",
  "service_name": "movie-reservation-mcp",
  "service_version": "test-version",
  "severity": "info",
  "tool_name": "reservation_health",
  "outcome": "success",
  "trace_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
}
```

Dynamic timestamp, span ID, and duration fields are omitted from this example.
Tests prove that downstream error bodies, exception details, and caller-selected
fault text do not enter these events.

## Infra reconciliation

Infra #57 still needs to:

- configure the dedicated loopback OTLP/HTTP receiver (planned port `4322`);
- verify native-to-AMP and CloudWatch translations with the real collector;
- accept the payload through all relevant filters and pipelines;
- verify X-Ray and optional Tempo routing for the connected trace;
- query fresh deployed series and preserve missing/idle/stale distinctions.
