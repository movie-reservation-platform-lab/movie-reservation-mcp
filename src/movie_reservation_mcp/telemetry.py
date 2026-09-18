from __future__ import annotations

import json
import logging
import os
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.metrics import MeterProvider as MeterProviderApi
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Span, SpanKind, Status, StatusCode
from opentelemetry.trace import TracerProvider as TracerProviderApi
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

SERVICE_NAME = "movie-reservation-mcp"
INSTRUMENTATION_SCOPE = "movie_reservation_mcp"
TOOL_CALLS_METRIC = "movie_reservation_mcp_tool_calls"
TOOL_DURATION_METRIC = "movie_reservation_mcp_tool_duration"
ALLOWED_TOOLS = frozenset(
    {
        "reservation_get_catalog",
        "reservation_request_seats",
        "reservation_get_request_status",
        "reservation_health",
    }
)
ALLOWED_OUTCOMES = frozenset({"success", "validation_error", "dependency_error", "internal_error"})
MAX_CORRELATION_FIELD_LENGTH = 128

_configured_telemetry: Telemetry | None = None


class JsonFormatter(logging.Formatter):
    def __init__(self, *, service_name: str, service_version: str) -> None:
        super().__init__()
        self._service_name = service_name
        self._service_version = service_version

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "severity": record.levelname.lower(),
            "service_name": self._service_name,
            "service_version": self._service_version,
            "event": getattr(record, "event", record.getMessage()),
            "message": record.getMessage(),
        }
        payload.update(current_trace_fields())
        for key, value in getattr(record, "fields", {}).items():
            if value is not None:
                payload[key] = value
        return json.dumps(payload, sort_keys=True, separators=(",", ":"))


class ToolObservation:
    def __init__(
        self,
        *,
        telemetry: Telemetry,
        tool_name: str,
        span: Span,
        started_at: float,
        log_fields: dict[str, str],
    ) -> None:
        self._telemetry = telemetry
        self._tool_name = tool_name
        self._span = span
        self._started_at = started_at
        self._log_fields = log_fields
        self._finished = False

    def finish(self, outcome: str, *, dependency_status: int | None = None) -> None:
        if self._finished:
            raise RuntimeError("tool observation already finished")
        if outcome not in ALLOWED_OUTCOMES:
            raise ValueError(f"unsupported tool outcome: {outcome}")

        duration_seconds = time.perf_counter() - self._started_at
        attributes = {"mcp.tool.name": self._tool_name, "outcome": outcome}
        self._telemetry.tool_calls.add(1, attributes)
        self._telemetry.tool_duration.record(duration_seconds, attributes)
        self._span.set_attribute("mcp.tool.outcome", outcome)
        if dependency_status is not None:
            self._span.set_attribute("dependency.http.response.status_code", dependency_status)

        if outcome == "success":
            self._span.set_status(Status(StatusCode.OK))
            level = logging.INFO
        else:
            self._span.set_status(Status(StatusCode.ERROR, outcome))
            level = logging.WARNING if outcome != "internal_error" else logging.ERROR

        self._telemetry.log(
            level,
            "mcp.tool.completed",
            "Reservation MCP tool completed.",
            tool_name=self._tool_name,
            outcome=outcome,
            duration_ms=round(duration_seconds * 1000, 3),
            dependency_status=dependency_status,
            **self._log_fields,
        )
        self._finished = True

    @property
    def finished(self) -> bool:
        return self._finished


class Telemetry:
    def __init__(
        self,
        *,
        tracer_provider: TracerProviderApi,
        meter_provider: MeterProviderApi,
        logger: logging.Logger,
    ) -> None:
        self.tracer_provider = tracer_provider
        self.meter_provider = meter_provider
        self.tracer = tracer_provider.get_tracer(INSTRUMENTATION_SCOPE)
        meter = meter_provider.get_meter(INSTRUMENTATION_SCOPE)
        self.tool_calls = meter.create_counter(
            TOOL_CALLS_METRIC,
            unit="{call}",
            description="Reservation MCP tool calls by bounded tool and outcome.",
        )
        self.tool_duration = meter.create_histogram(
            TOOL_DURATION_METRIC,
            unit="s",
            description="Reservation MCP tool call duration in seconds.",
        )
        self._logger = logger

    @contextmanager
    def tool_call(
        self,
        tool_name: str,
        *,
        traceparent: str | None = None,
        tracestate: str | None = None,
        correlation_id: str | None = None,
        request_id: str | None = None,
    ) -> Iterator[ToolObservation]:
        if tool_name not in ALLOWED_TOOLS:
            raise ValueError(f"unsupported tool name: {tool_name}")

        carrier = {
            key: value.strip()
            for key, value in {"traceparent": traceparent, "tracestate": tracestate}.items()
            if value is not None and value.strip()
        }
        parent_context = TraceContextTextMapPropagator().extract(carrier=carrier)
        log_fields = bounded_correlation_fields(correlation_id=correlation_id, request_id=request_id)
        started_at = time.perf_counter()

        with self.tracer.start_as_current_span(
            f"mcp.tool.{tool_name}",
            context=parent_context,
            kind=SpanKind.SERVER,
            attributes={"mcp.tool.name": tool_name, **log_fields},
        ) as span:
            observation = ToolObservation(
                telemetry=self,
                tool_name=tool_name,
                span=span,
                started_at=started_at,
                log_fields=log_fields,
            )
            self.log(
                logging.INFO,
                "mcp.tool.started",
                "Reservation MCP tool started.",
                tool_name=tool_name,
                **log_fields,
            )
            try:
                yield observation
            except Exception as exc:
                if not observation.finished:
                    span.record_exception(exc)
                    observation.finish("internal_error")
                raise
            finally:
                if not observation.finished:
                    observation.finish("internal_error")

    def log(self, level: int, event: str, message: str, **fields: Any) -> None:
        self._logger.log(level, message, extra={"event": event, "fields": fields})


def configure_telemetry() -> Telemetry:
    global _configured_telemetry
    if _configured_telemetry is not None:
        return _configured_telemetry

    service_name = os.getenv("OTEL_SERVICE_NAME", SERVICE_NAME)
    service_version = os.getenv("SERVICE_VERSION", "unknown")
    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": os.getenv("SERVICE_NAMESPACE", "movie-platform"),
            "service.version": service_version,
            "deployment.environment.name": os.getenv("DEPLOYMENT_ENVIRONMENT", "local"),
        }
    )
    logger = configure_logging(service_name=service_name, service_version=service_version)

    tracer_provider = TracerProvider(resource=resource)
    metric_readers = []
    if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        try:
            tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
            metric_readers.append(PeriodicExportingMetricReader(OTLPMetricExporter()))
        except Exception:
            logger.exception(
                "OpenTelemetry exporter configuration failed; continuing without export.",
                extra={"event": "telemetry.exporter.configuration_failed", "fields": {}},
            )

    meter_provider = MeterProvider(resource=resource, metric_readers=metric_readers)
    trace.set_tracer_provider(tracer_provider)
    metrics.set_meter_provider(meter_provider)

    _configured_telemetry = Telemetry(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger=logger,
    )
    return _configured_telemetry


def configure_logging(*, service_name: str, service_version: str) -> logging.Logger:
    logger = logging.getLogger(INSTRUMENTATION_SCOPE)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter(service_name=service_name, service_version=service_version))
        logger.addHandler(handler)
    logger.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    logger.propagate = False
    return logger


def bounded_correlation_fields(*, correlation_id: str | None, request_id: str | None) -> dict[str, str]:
    fields: dict[str, str] = {}
    if value := bounded_field(correlation_id):
        fields["correlation_id"] = value
    if value := bounded_field(request_id):
        fields["request_id"] = value
    return fields


def bounded_field(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped[:MAX_CORRELATION_FIELD_LENGTH] or None


def current_trace_fields() -> dict[str, str]:
    context = trace.get_current_span().get_span_context()
    if not context.is_valid:
        return {}
    return {"trace_id": f"{context.trace_id:032x}", "span_id": f"{context.span_id:016x}"}
