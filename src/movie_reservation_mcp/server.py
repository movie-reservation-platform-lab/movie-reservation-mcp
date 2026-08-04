from __future__ import annotations

import os
from dataclasses import dataclass


SERVICE_NAME = "movie-reservation-mcp"
DEFAULT_GRAPHQL_URL = "http://127.0.0.1:3000/graphql"


@dataclass(frozen=True)
class ReservationMcpSettings:
    graphql_url: str


def load_settings() -> ReservationMcpSettings:
    return ReservationMcpSettings(
        graphql_url=os.getenv("MOVIE_RESERVATION_GRAPHQL_URL", DEFAULT_GRAPHQL_URL),
    )


def main() -> None:
    settings = load_settings()
    print(f"{SERVICE_NAME} scaffold configured for {settings.graphql_url}")


if __name__ == "__main__":
    main()
