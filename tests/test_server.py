from __future__ import annotations

from typing import Any

import pytest

from movie_reservation_mcp import server
from movie_reservation_mcp.reservation_client import RequestMetadata, ReservationClientError


class FakeReservationClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def get_catalog(self, *, movie_id: str | None, metadata: RequestMetadata) -> dict[str, Any]:
        self.calls.append(("get_catalog", {"movie_id": movie_id, "metadata": metadata}))
        return {"movies": [{"id": "movie-1"}], "screenings": [{"id": "screening-1"}]}

    async def request_seats(
        self,
        *,
        screening_id: str,
        seat_ids: list[str],
        metadata: RequestMetadata,
    ) -> dict[str, Any]:
        self.calls.append(
            (
                "request_seats",
                {"screening_id": screening_id, "seat_ids": seat_ids, "metadata": metadata},
            )
        )
        return {"requestReservation": {"id": "request-1", "status": "REQUESTED"}}

    async def get_request_status(self, *, request_id: str, metadata: RequestMetadata) -> dict[str, Any]:
        self.calls.append(("get_request_status", {"request_id": request_id, "metadata": metadata}))
        return {
            "reservationRequestStatus": {"id": request_id, "status": "CONFIRMED"},
            "reservationResult": {"id": "reservation-1"},
        }

    async def health(self, metadata: RequestMetadata) -> dict[str, Any]:
        self.calls.append(("health", {"metadata": metadata}))
        return {"status": "ok"}


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> FakeReservationClient:
    client = FakeReservationClient()
    monkeypatch.setattr(server, "client", client)
    return client


@pytest.mark.asyncio
async def test_tool_names_are_frozen() -> None:
    tools = await server.mcp.list_tools()

    assert {tool.name for tool in tools} == {
        "reservation_get_catalog",
        "reservation_request_seats",
        "reservation_get_request_status",
        "reservation_health",
    }


@pytest.mark.asyncio
async def test_catalog_maps_data_and_propagates_context(fake_client: FakeReservationClient) -> None:
    result = await server.reservation_get_catalog(
        movie_id=" movie-1 ",
        fault="ignored",
        demo_fault="reservation-timeout",
        traceparent="00-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa-bbbbbbbbbbbbbbbb-01",
        correlation_id="correlation-1",
    )

    assert result["catalog"]["movies"] == [{"id": "movie-1"}]
    assert result["fault"] == "reservation-timeout"
    call_name, call = fake_client.calls[0]
    assert call_name == "get_catalog"
    assert call["movie_id"] == " movie-1 "
    assert call["metadata"].demo_fault == "reservation-timeout"
    assert call["metadata"].correlation_id == "correlation-1"


@pytest.mark.asyncio
async def test_request_seats_normalizes_input(fake_client: FakeReservationClient) -> None:
    result = await server.reservation_request_seats(
        screening_id=" screening-1 ",
        seat_ids=[" seat-1 ", "", "  ", "seat-2"],
    )

    assert result["ok"] is True
    _, call = fake_client.calls[0]
    assert call["screening_id"] == "screening-1"
    assert call["seat_ids"] == ["seat-1", "seat-2"]


@pytest.mark.asyncio
async def test_request_seats_rejects_blank_input_without_calling_dependency(
    fake_client: FakeReservationClient,
) -> None:
    result = await server.reservation_request_seats(screening_id=" ", seat_ids=[" "])

    assert result["ok"] is False
    assert result["error"] == "screening_id is required"
    assert fake_client.calls == []


@pytest.mark.asyncio
async def test_request_status_maps_request_and_reservation(fake_client: FakeReservationClient) -> None:
    result = await server.reservation_get_request_status(reservation_request_id=" request-1 ")

    assert result["found"] is True
    assert result["reservation_request"]["status"] == "CONFIRMED"
    assert result["reservation"]["id"] == "reservation-1"


@pytest.mark.asyncio
async def test_downstream_error_is_bounded(fake_client: FakeReservationClient) -> None:
    async def fail_catalog(*, movie_id: str | None, metadata: RequestMetadata) -> dict[str, Any]:
        raise ReservationClientError(500, {"errors": [{"message": "sensitive downstream detail"}]})

    fake_client.get_catalog = fail_catalog  # type: ignore[method-assign]

    result = await server.reservation_get_catalog()

    assert result == {
        "ok": False,
        "service_name": "movie-reservation-mcp",
        "tool_name": "reservation_get_catalog",
        "fault": "none",
        "status_code": 500,
        "error": "reservation_dependency_failed",
    }
