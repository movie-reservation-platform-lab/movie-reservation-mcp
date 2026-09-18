from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import StatusCode

from movie_reservation_mcp import server
from movie_reservation_mcp.reservation_client import ReservationClient, ReservationClientSettings
from movie_reservation_mcp.telemetry import (
    MAX_CORRELATION_FIELD_LENGTH,
    TOOL_CALLS_METRIC,
    TOOL_DURATION_METRIC,
    JsonFormatter,
    Telemetry,
    build_resource,
)

INCOMING_TRACE_ID = "a" * 32
INCOMING_SPAN_ID = "b" * 16
INCOMING_TRACEPARENT = f"00-{INCOMING_TRACE_ID}-{INCOMING_SPAN_ID}-01"


@pytest.mark.asyncio
async def test_tool_and_http_spans_join_incoming_trace_and_inject_child_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(200, json={"data": {"movies": [], "screenings": []}})

    with telemetry_harness() as harness:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        reservation_client = ReservationClient(
            settings=ReservationClientSettings(
                graphql_url="https://reservation.example.test/graphql",
                health_url="https://reservation.example.test/health",
            ),
            http_client=http_client,
            tracer_provider=harness.tracer_provider,
            meter_provider=harness.meter_provider,
        )
        monkeypatch.setattr(server, "telemetry", harness.telemetry)
        monkeypatch.setattr(server, "client", reservation_client)

        try:
            result = await server.reservation_get_catalog(
                traceparent=INCOMING_TRACEPARENT,
                tracestate="vendor=value",
                correlation_id="correlation-1",
                request_id="request-1",
            )
        finally:
            await reservation_client.close()

        assert result["ok"] is True
        spans = harness.span_exporter.get_finished_spans()
        tool_span = next(span for span in spans if span.name == "mcp.tool.reservation_get_catalog")
        http_span = next(span for span in spans if span.kind.name == "CLIENT")
        assert f"{tool_span.context.trace_id:032x}" == INCOMING_TRACE_ID
        assert tool_span.parent is not None
        assert f"{tool_span.parent.span_id:016x}" == INCOMING_SPAN_ID
        assert http_span.parent is not None
        assert http_span.parent.span_id == tool_span.context.span_id
        assert captured_request is not None
        downstream_traceparent = captured_request.headers["traceparent"]
        assert downstream_traceparent.split("-")[1] == INCOMING_TRACE_ID
        assert downstream_traceparent.split("-")[2] == f"{http_span.context.span_id:016x}"
        assert downstream_traceparent != INCOMING_TRACEPARENT
        assert captured_request.headers["tracestate"] == "vendor=value"

        call_points = metric_points(harness.metric_reader, TOOL_CALLS_METRIC)
        assert [(point.value, dict(point.attributes)) for point in call_points] == [
            (1, {"mcp.tool.name": "reservation_get_catalog", "outcome": "success"})
        ]
        resource = harness.metric_reader.get_metrics_data().resource_metrics[0].resource.attributes
        assert resource["service.name"] == "movie-reservation-mcp"
        assert resource["service.namespace"] == "movie-platform"
        assert resource["service.version"] == "test-version"
        assert resource["deployment.environment.name"] == "test"


@pytest.mark.asyncio
async def test_validation_and_graphql_failures_have_bounded_distinct_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "private database detail"}]})

    with telemetry_harness() as harness:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        reservation_client = ReservationClient(
            settings=ReservationClientSettings(
                graphql_url="https://reservation.example.test/graphql",
                health_url="https://reservation.example.test/health",
            ),
            http_client=http_client,
            tracer_provider=harness.tracer_provider,
            meter_provider=harness.meter_provider,
        )
        monkeypatch.setattr(server, "telemetry", harness.telemetry)
        monkeypatch.setattr(server, "client", reservation_client)

        try:
            validation = await server.reservation_request_seats(screening_id=" ", seat_ids=[])
            dependency = await server.reservation_get_catalog(
                fault="caller-controlled-fault-value",
                correlation_id="c" * 500,
            )
        finally:
            await reservation_client.close()

        assert validation["error"] == "screening_id is required"
        assert dependency["error"] == "reservation_dependency_failed"
        call_attributes = [dict(point.attributes) for point in metric_points(harness.metric_reader, TOOL_CALLS_METRIC)]
        assert call_attributes == [
            {"mcp.tool.name": "reservation_request_seats", "outcome": "validation_error"},
            {"mcp.tool.name": "reservation_get_catalog", "outcome": "dependency_error"},
        ]
        assert all(set(attributes) == {"mcp.tool.name", "outcome"} for attributes in call_attributes)

        tool_spans = [span for span in harness.span_exporter.get_finished_spans() if span.kind.name == "SERVER"]
        assert [span.status.status_code for span in tool_spans] == [StatusCode.ERROR, StatusCode.ERROR]
        assert tool_spans[1].attributes["correlation_id"] == "c" * MAX_CORRELATION_FIELD_LENGTH
        assert "caller-controlled-fault-value" not in harness.log_stream.getvalue()
        assert "private database detail" not in harness.log_stream.getvalue()


@pytest.mark.asyncio
async def test_transport_timeout_is_a_dependency_outcome(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("private network detail", request=request)

    with telemetry_harness() as harness:
        http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        reservation_client = ReservationClient(
            settings=ReservationClientSettings(
                graphql_url="https://reservation.example.test/graphql",
                health_url="https://reservation.example.test/health",
            ),
            http_client=http_client,
            tracer_provider=harness.tracer_provider,
            meter_provider=harness.meter_provider,
        )
        monkeypatch.setattr(server, "telemetry", harness.telemetry)
        monkeypatch.setattr(server, "client", reservation_client)

        try:
            result = await server.reservation_health()
        finally:
            await reservation_client.close()

        assert result["status_code"] == 502
        assert result["error"] == "reservation_dependency_failed"
        call_points = metric_points(harness.metric_reader, TOOL_CALLS_METRIC)
        assert [(point.value, dict(point.attributes)) for point in call_points] == [
            (1, {"mcp.tool.name": "reservation_health", "outcome": "dependency_error"})
        ]
        assert "private network detail" not in harness.log_stream.getvalue()


def test_no_exporter_tool_call_records_locally_without_failing() -> None:
    resource = Resource.create({"service.name": "movie-reservation-mcp"})
    tracer_provider = TracerProvider(resource=resource)
    meter_provider = MeterProvider(resource=resource)
    logger = logging.getLogger("test.reservation-mcp.no-exporter")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    telemetry = Telemetry(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger=logger,
    )

    with telemetry.tool_call("reservation_health") as observation:
        observation.finish("success")


def test_resource_preserves_platform_owned_otel_attributes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SERVICE_NAMESPACE", raising=False)
    monkeypatch.delenv("DEPLOYMENT_ENVIRONMENT", raising=False)
    monkeypatch.setenv(
        "OTEL_RESOURCE_ATTRIBUTES",
        "service.namespace=movie-reservation-platform,deployment.environment.name=aws-demo",
    )

    resource = build_resource(service_name="movie-reservation-mcp", service_version="release-1")

    assert resource.attributes["service.name"] == "movie-reservation-mcp"
    assert resource.attributes["service.namespace"] == "movie-reservation-platform"
    assert resource.attributes["service.version"] == "release-1"
    assert resource.attributes["deployment.environment.name"] == "aws-demo"


def test_correlated_json_log_has_canonical_identity_and_active_trace() -> None:
    with telemetry_harness() as harness:
        with harness.telemetry.tool_call(
            "reservation_health",
            traceparent=INCOMING_TRACEPARENT,
            correlation_id="correlation-1",
            request_id="request-1",
        ) as observation:
            observation.finish("success")

        events = [json.loads(line) for line in harness.log_stream.getvalue().splitlines()]
        completed = next(event for event in events if event["event"] == "mcp.tool.completed")
        assert completed["service_name"] == "movie-reservation-mcp"
        assert completed["service_version"] == "test-version"
        assert completed["trace_id"] == INCOMING_TRACE_ID
        assert completed["span_id"] != INCOMING_SPAN_ID
        assert completed["correlation_id"] == "correlation-1"
        assert completed["request_id"] == "request-1"
        assert completed["outcome"] == "success"

        duration_points = metric_points(harness.metric_reader, TOOL_DURATION_METRIC)
        assert len(duration_points) == 1
        assert duration_points[0].count == 1
        assert duration_points[0].sum >= 0
        assert dict(duration_points[0].attributes) == {
            "mcp.tool.name": "reservation_health",
            "outcome": "success",
        }


class TelemetryHarness:
    def __init__(self) -> None:
        resource = Resource.create(
            {
                "service.name": "movie-reservation-mcp",
                "service.namespace": "movie-platform",
                "service.version": "test-version",
                "deployment.environment.name": "test",
            }
        )
        self.span_exporter = InMemorySpanExporter()
        self.tracer_provider = TracerProvider(resource=resource)
        self.tracer_provider.add_span_processor(SimpleSpanProcessor(self.span_exporter))
        self.metric_reader = InMemoryMetricReader()
        self.meter_provider = MeterProvider(resource=resource, metric_readers=[self.metric_reader])
        self.log_stream = io.StringIO()
        logger = logging.getLogger(f"test.reservation-mcp.{id(self)}")
        logger.handlers.clear()
        handler = logging.StreamHandler(self.log_stream)
        handler.setFormatter(JsonFormatter(service_name="movie-reservation-mcp", service_version="test-version"))
        logger.addHandler(handler)
        logger.propagate = False
        logger.setLevel(logging.INFO)
        self.telemetry = Telemetry(
            tracer_provider=self.tracer_provider,
            meter_provider=self.meter_provider,
            logger=logger,
        )

    def close(self) -> None:
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()


@contextmanager
def telemetry_harness() -> Iterator[TelemetryHarness]:
    harness = TelemetryHarness()
    try:
        yield harness
    finally:
        harness.close()


def metric_points(reader: InMemoryMetricReader, metric_name: str) -> list[Any]:
    metrics_data = reader.get_metrics_data()
    assert metrics_data is not None
    return [
        point
        for resource_metrics in metrics_data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == metric_name
        for point in metric.data.data_points
    ]
