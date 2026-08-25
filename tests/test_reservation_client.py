from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from movie_reservation_mcp.reservation_client import (
    RequestMetadata,
    ReservationClient,
    ReservationClientError,
    ReservationClientSettings,
    derive_health_url,
)


def test_headers_preserve_propagation_field_names() -> None:
    metadata = RequestMetadata(
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        tracestate="vendor=value",
        correlation_id="correlation-1",
        request_id="request-1",
        demo_fault="reservation-timeout",
    )

    assert metadata.headers() == {
        "traceparent": "00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        "tracestate": "vendor=value",
        "X-Correlation-Id": "correlation-1",
        "X-Request-Id": "request-1",
        "X-Demo-Fault": "reservation-timeout",
    }


def test_headers_skip_blank_values() -> None:
    metadata = RequestMetadata(traceparent=" ", correlation_id="correlation-1")

    assert metadata.headers() == {"X-Correlation-Id": "correlation-1"}


def test_derive_health_url_from_default_graphql_path() -> None:
    assert derive_health_url("http://127.0.0.1:3000/graphql") == "http://127.0.0.1:3000/health"


def test_derive_health_url_from_nested_graphql_path() -> None:
    assert derive_health_url("https://example.test/reservation/graphql") == "https://example.test/reservation/health"


@pytest.mark.asyncio
async def test_get_catalog_posts_graphql_query_with_propagation_headers() -> None:
    captured_request: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_request
        captured_request = request
        return httpx.Response(
            200,
            json={"data": {"movies": [{"id": "movie-1"}], "screenings": [{"id": "screening-1"}]}},
        )

    client = create_test_client(handler)

    try:
        data = await client.get_catalog(
            movie_id="movie-1",
            metadata=RequestMetadata(correlation_id="correlation-1"),
        )
    finally:
        await client.close()

    assert data == {"movies": [{"id": "movie-1"}], "screenings": [{"id": "screening-1"}]}
    assert captured_request is not None
    assert captured_request.headers["X-Correlation-Id"] == "correlation-1"
    assert captured_request.url == httpx.URL("https://reservation.example.test/graphql")
    assert captured_request.method == "POST"
    payload = read_json_request(captured_request)
    assert payload["operationName"] == "ReservationMcpGetCatalog"
    assert payload["variables"] == {"movieId": "movie-1"}


@pytest.mark.asyncio
async def test_request_seats_posts_mutation_input() -> None:
    captured_payload: dict[str, Any] | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured_payload
        captured_payload = read_json_request(request)
        return httpx.Response(
            200,
            json={
                "data": {
                    "requestReservation": {
                        "id": "request-1",
                        "screeningId": "screening-1",
                        "seatIds": ["seat-1"],
                        "status": "REQUESTED",
                    }
                }
            },
        )

    client = create_test_client(handler)

    try:
        data = await client.request_seats(
            screening_id="screening-1",
            seat_ids=["seat-1"],
            metadata=RequestMetadata(),
        )
    finally:
        await client.close()

    assert data["requestReservation"]["id"] == "request-1"
    assert captured_payload is not None
    assert captured_payload["operationName"] == "ReservationMcpRequestSeats"
    assert captured_payload["variables"] == {"input": {"screeningId": "screening-1", "seatIds": ["seat-1"]}}


@pytest.mark.asyncio
async def test_graphql_errors_raise_client_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "bad request"}]})

    client = create_test_client(handler)

    try:
        with pytest.raises(ReservationClientError) as raised:
            await client.get_request_status(request_id="request-1", metadata=RequestMetadata())
    finally:
        await client.close()

    assert raised.value.status_code == 200
    assert raised.value.payload == {"errors": [{"message": "bad request"}]}


@pytest.mark.asyncio
async def test_transport_errors_become_stable_client_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection details must not escape", request=request)

    client = create_test_client(handler)

    try:
        with pytest.raises(ReservationClientError) as raised:
            await client.health(RequestMetadata())
    finally:
        await client.close()

    assert raised.value.status_code == 502
    assert raised.value.payload == {"error": "dependency_unavailable"}


@pytest.mark.asyncio
async def test_invalid_json_becomes_stable_client_error() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="internal response details")

    client = create_test_client(handler)

    try:
        with pytest.raises(ReservationClientError) as raised:
            await client.health(RequestMetadata())
    finally:
        await client.close()

    assert raised.value.status_code == 200
    assert raised.value.payload == {"error": "invalid_dependency_response"}


def create_test_client(handler: Callable[[httpx.Request], httpx.Response]) -> ReservationClient:
    transport = httpx.MockTransport(handler)
    return ReservationClient(
        settings=ReservationClientSettings(
            graphql_url="https://reservation.example.test/graphql",
            health_url="https://reservation.example.test/health",
        ),
        http_client=httpx.AsyncClient(transport=transport),
    )


def read_json_request(request: httpx.Request) -> dict[str, Any]:
    return json.loads(request.content.decode("utf-8"))
