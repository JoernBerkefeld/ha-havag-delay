"""Async client for the INSA HAFAS endpoint."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import aiohttp

from .hafas import (
    ENDPOINT,
    Departure,
    Stop,
    build_location_request,
    build_station_board_request,
    parse_departures,
    parse_stops,
)

_TIMEOUT = aiohttp.ClientTimeout(total=15)


class HavagClient:
    """Fetches live data. Every call hits the endpoint; nothing is cached."""

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session

    async def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        async with self._session.post(ENDPOINT, json=body, timeout=_TIMEOUT) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def async_departures(self, stop_id: str, now: datetime, duration: int = 60) -> list[Departure]:
        """Departures of a stop within the next ``duration`` minutes."""
        return parse_departures(await self._post(build_station_board_request(stop_id, now, duration)))

    async def async_search_stops(self, query: str) -> list[Stop]:
        """Stops matching a name."""
        return parse_stops(await self._post(build_location_request(query)))
