from __future__ import annotations

import os
from typing import Any

from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse

from movie_reservation_mcp.reservation_client import (
    RequestMetadata,
    ReservationClient,
    ReservationClientError,
)

SERVICE_NAME = "movie-reservation-mcp"
DEFAULT_HOST = "0.0.0.0"
DEFAULT_PORT = 8091

mcp = FastMCP("Movie Reservation MCP")
client = ReservationClient()


@mcp.custom_route("/health", methods=["GET"])
async def health_check(_request: Request) -> JSONResponse:
    try:
        downstream = await client.health(RequestMetadata())
    except ReservationClientError:
        return JSONResponse(
            {
                "status": "degraded",
                "service_name": SERVICE_NAME,
                "downstream": {"status": "unavailable"},
            },
            status_code=503,
        )

    return JSONResponse(
        {
            "status": "ok",
            "service_name": SERVICE_NAME,
            "downstream": downstream,
        }
    )


@mcp.tool
async def reservation_get_catalog(
    movie_id: str | None = None,
    fault: str | None = None,
    traceparent: str | None = None,
    tracestate: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    demo_fault: str | None = None,
) -> dict[str, Any]:
    """Return movies and scheduled screenings from the reservation GraphQL API."""

    effective_fault = demo_fault or fault
    try:
        data = await client.get_catalog(
            movie_id=movie_id,
            metadata=build_metadata(
                traceparent=traceparent,
                tracestate=tracestate,
                correlation_id=correlation_id,
                request_id=request_id,
                demo_fault=effective_fault,
            ),
        )
    except ReservationClientError as exc:
        return downstream_error("reservation_get_catalog", effective_fault, exc)

    return {
        "ok": True,
        "service_name": SERVICE_NAME,
        "fault": effective_fault or "none",
        "catalog": {
            "movies": data.get("movies", []),
            "screenings": data.get("screenings", []),
        },
    }


@mcp.tool
async def reservation_request_seats(
    screening_id: str,
    seat_ids: list[str],
    fault: str | None = None,
    traceparent: str | None = None,
    tracestate: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    demo_fault: str | None = None,
) -> dict[str, Any]:
    """Create an asynchronous reservation request for seats in a screening."""

    effective_fault = demo_fault or fault
    cleaned_seat_ids = [seat_id.strip() for seat_id in seat_ids if seat_id.strip()]
    if not screening_id.strip():
        return validation_error("reservation_request_seats", effective_fault, "screening_id is required")

    if not cleaned_seat_ids:
        return validation_error(
            "reservation_request_seats",
            effective_fault,
            "seat_ids must contain at least one seat id",
        )

    try:
        data = await client.request_seats(
            screening_id=screening_id.strip(),
            seat_ids=cleaned_seat_ids,
            metadata=build_metadata(
                traceparent=traceparent,
                tracestate=tracestate,
                correlation_id=correlation_id,
                request_id=request_id,
                demo_fault=effective_fault,
            ),
        )
    except ReservationClientError as exc:
        return downstream_error("reservation_request_seats", effective_fault, exc)

    return {
        "ok": True,
        "service_name": SERVICE_NAME,
        "fault": effective_fault or "none",
        "reservation_request": data.get("requestReservation"),
    }


@mcp.tool
async def reservation_get_request_status(
    reservation_request_id: str | None = None,
    request_id: str | None = None,
    fault: str | None = None,
    traceparent: str | None = None,
    tracestate: str | None = None,
    correlation_id: str | None = None,
    demo_fault: str | None = None,
) -> dict[str, Any]:
    """Return a reservation request status and confirmed reservation when available."""

    effective_fault = demo_fault or fault
    if reservation_request_id is None or not reservation_request_id.strip():
        return validation_error(
            "reservation_get_request_status",
            effective_fault,
            "reservation_request_id is required",
        )

    try:
        data = await client.get_request_status(
            request_id=reservation_request_id.strip(),
            metadata=build_metadata(
                traceparent=traceparent,
                tracestate=tracestate,
                correlation_id=correlation_id,
                request_id=request_id,
                demo_fault=effective_fault,
            ),
        )
    except ReservationClientError as exc:
        return downstream_error("reservation_get_request_status", effective_fault, exc)

    reservation_request = data.get("reservationRequestStatus")
    return {
        "ok": True,
        "service_name": SERVICE_NAME,
        "fault": effective_fault or "none",
        "found": reservation_request is not None,
        "reservation_request": reservation_request,
        "reservation": data.get("reservationResult"),
    }


@mcp.tool
async def reservation_health(
    traceparent: str | None = None,
    tracestate: str | None = None,
    correlation_id: str | None = None,
    request_id: str | None = None,
    demo_fault: str | None = None,
) -> dict[str, Any]:
    """Return the downstream reservation API health response."""

    try:
        payload = await client.health(
            build_metadata(
                traceparent=traceparent,
                tracestate=tracestate,
                correlation_id=correlation_id,
                request_id=request_id,
                demo_fault=demo_fault,
            )
        )
    except ReservationClientError as exc:
        return downstream_error("reservation_health", demo_fault, exc)

    return {
        "ok": True,
        "service_name": SERVICE_NAME,
        "fault": demo_fault or "none",
        "health": payload,
    }


def build_metadata(
    *,
    traceparent: str | None,
    tracestate: str | None,
    correlation_id: str | None,
    request_id: str | None,
    demo_fault: str | None,
) -> RequestMetadata:
    return RequestMetadata(
        traceparent=traceparent,
        tracestate=tracestate,
        correlation_id=correlation_id,
        request_id=request_id,
        demo_fault=demo_fault,
    )


def validation_error(tool_name: str, fault: str | None, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "service_name": SERVICE_NAME,
        "tool_name": tool_name,
        "fault": fault or "none",
        "error": message,
    }


def downstream_error(tool_name: str, fault: str | None, error: ReservationClientError) -> dict[str, Any]:
    return {
        "ok": False,
        "service_name": SERVICE_NAME,
        "tool_name": tool_name,
        "fault": fault or "none",
        "status_code": error.status_code,
        "error": "reservation_dependency_failed",
    }


def main() -> None:
    host = os.getenv("HOST", DEFAULT_HOST)
    port = int(os.getenv("PORT", str(DEFAULT_PORT)))
    mcp.run(transport="http", host=host, port=port, path="/mcp")


if __name__ == "__main__":
    main()
