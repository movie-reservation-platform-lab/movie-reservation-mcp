from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx

DEFAULT_GRAPHQL_URL = "http://127.0.0.1:3000/graphql"
DEFAULT_TIMEOUT_SECONDS = 10.0
PROPAGATED_HEADERS = {
    "traceparent": "traceparent",
    "tracestate": "tracestate",
    "correlation_id": "X-Correlation-Id",
    "request_id": "X-Request-Id",
    "demo_fault": "X-Demo-Fault",
}

GET_CATALOG_QUERY = """
query ReservationMcpGetCatalog($movieId: ID) {
  movies {
    id
    title
    durationMinutes
    rating
  }
  screenings(movieId: $movieId) {
    id
    movieId
    auditoriumId
    startsAt
    endsAt
    seats {
      id
      row
      number
    }
  }
}
"""

REQUEST_SEATS_MUTATION = """
mutation ReservationMcpRequestSeats($input: RequestReservationInput!) {
  requestReservation(input: $input) {
    id
    requestedByUserId
    screeningId
    seatIds
    status
  }
}
"""

GET_REQUEST_STATUS_QUERY = """
query ReservationMcpGetRequestStatus($id: ID!) {
  reservationRequestStatus(id: $id) {
    id
    requestedByUserId
    screeningId
    seatIds
    status
  }
  reservationResult(requestId: $id) {
    id
    reservationRequestId
    reservedByUserId
    screeningId
    seatIds
    confirmedAt
  }
}
"""


class ReservationClientError(RuntimeError):
    def __init__(self, status_code: int, payload: dict[str, Any]) -> None:
        self.status_code = status_code
        self.payload = payload
        super().__init__(f"Reservation API returned HTTP {status_code}")


@dataclass(frozen=True)
class RequestMetadata:
    traceparent: str | None = None
    tracestate: str | None = None
    correlation_id: str | None = None
    request_id: str | None = None
    demo_fault: str | None = None

    def headers(self) -> dict[str, str]:
        values = {
            "traceparent": self.traceparent,
            "tracestate": self.tracestate,
            "correlation_id": self.correlation_id,
            "request_id": self.request_id,
            "demo_fault": self.demo_fault,
        }
        return {
            header_name: value
            for field_name, header_name in PROPAGATED_HEADERS.items()
            if (value := values[field_name]) is not None and value.strip()
        }


@dataclass(frozen=True)
class ReservationClientSettings:
    graphql_url: str
    health_url: str
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS


def load_client_settings() -> ReservationClientSettings:
    graphql_url = os.getenv("MOVIE_RESERVATION_GRAPHQL_URL", DEFAULT_GRAPHQL_URL)
    health_url = os.getenv("MOVIE_RESERVATION_HEALTH_URL", derive_health_url(graphql_url))
    timeout_seconds = float(os.getenv("MOVIE_RESERVATION_API_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    return ReservationClientSettings(
        graphql_url=graphql_url,
        health_url=health_url,
        timeout_seconds=timeout_seconds,
    )


def derive_health_url(graphql_url: str) -> str:
    parsed = urlsplit(graphql_url)
    path = parsed.path.rstrip("/").removesuffix("/graphql")

    health_path = f"{path}/health" if path else "/health"
    return urlunsplit((parsed.scheme, parsed.netloc, health_path, "", ""))


class ReservationClient:
    def __init__(
        self,
        settings: ReservationClientSettings | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._settings = settings or load_client_settings()
        self._client = http_client or httpx.AsyncClient(timeout=self._settings.timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def health(self, metadata: RequestMetadata) -> dict[str, Any]:
        try:
            response = await self._client.get(self._settings.health_url, headers=metadata.headers())
        except httpx.HTTPError as exc:
            raise dependency_unavailable_error() from exc
        return parse_http_response(response)

    async def get_catalog(self, *, movie_id: str | None, metadata: RequestMetadata) -> dict[str, Any]:
        variables: dict[str, Any] = {"movieId": nonblank_or_none(movie_id)}
        return await self._graphql(
            operation_name="ReservationMcpGetCatalog",
            query=GET_CATALOG_QUERY,
            variables=variables,
            metadata=metadata,
        )

    async def request_seats(
        self,
        *,
        screening_id: str,
        seat_ids: list[str],
        metadata: RequestMetadata,
    ) -> dict[str, Any]:
        return await self._graphql(
            operation_name="ReservationMcpRequestSeats",
            query=REQUEST_SEATS_MUTATION,
            variables={
                "input": {
                    "screeningId": screening_id,
                    "seatIds": seat_ids,
                }
            },
            metadata=metadata,
        )

    async def get_request_status(self, *, request_id: str, metadata: RequestMetadata) -> dict[str, Any]:
        return await self._graphql(
            operation_name="ReservationMcpGetRequestStatus",
            query=GET_REQUEST_STATUS_QUERY,
            variables={"id": request_id},
            metadata=metadata,
        )

    async def _graphql(
        self,
        *,
        operation_name: str,
        query: str,
        variables: dict[str, Any],
        metadata: RequestMetadata,
    ) -> dict[str, Any]:
        try:
            response = await self._client.post(
                self._settings.graphql_url,
                json={
                    "operationName": operation_name,
                    "query": query,
                    "variables": variables,
                },
                headers=metadata.headers(),
            )
        except httpx.HTTPError as exc:
            raise dependency_unavailable_error() from exc
        payload = parse_http_response(response)
        if payload.get("errors"):
            raise ReservationClientError(response.status_code, payload)

        data = payload.get("data")
        if not isinstance(data, dict):
            raise ReservationClientError(response.status_code, payload)

        return data


def parse_http_response(response: httpx.Response) -> dict[str, Any]:
    try:
        payload = response.json()
    except ValueError as exc:
        raise ReservationClientError(
            response.status_code,
            {"error": "invalid_dependency_response"},
        ) from exc

    if not isinstance(payload, dict):
        payload = {"payload": payload}

    if response.status_code >= 400:
        raise ReservationClientError(response.status_code, payload)

    return payload


def dependency_unavailable_error() -> ReservationClientError:
    return ReservationClientError(502, {"error": "dependency_unavailable"})


def nonblank_or_none(value: str | None) -> str | None:
    if value is None:
        return None

    stripped = value.strip()
    return stripped or None
