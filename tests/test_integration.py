"""Config flow and action tests, run inside a Home Assistant test instance."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.havag_delay.const import DOMAIN
from custom_components.havag_delay.hafas import Departure, HafasError, Stop

STOP = Stop("3937", "Halle (Saale), Betriebshof Freiimfelder Str.")
DIR = "Halle (Saale), Soltauer Str."
ENTRY_DATA = {
    "stop_id": "3937",
    "stop_name": STOP.name,
    "line": "10",
    "direction": "Soltauer Str.",
}
SEARCH = "custom_components.havag_delay.config_flow.HavagClient.async_search_stops"
BOARD = "custom_components.havag_delay.HavagClient.async_departures"


async def _start_flow(hass: HomeAssistant, search):
    with patch(SEARCH, search):
        result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
        assert result["type"] is FlowResultType.FORM
        return await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"stop_query": "Freiimfelder", "line": "10", "direction": "Soltauer Str."},
        )


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    result = await _start_flow(hass, AsyncMock(return_value=[STOP]))
    assert result["step_id"] == "pick_stop"
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_id": "3937"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    assert result["title"] == "Linie 10 · Halle (Saale), Betriebshof Freiimfelder Str. → Soltauer Str."


@pytest.mark.parametrize(
    ("search", "error"),
    [
        (AsyncMock(return_value=[]), "no_results"),
        (AsyncMock(side_effect=aiohttp.ClientError), "cannot_connect"),
        (AsyncMock(side_effect=HafasError("AUTH")), "cannot_connect"),
    ],
)
async def test_config_flow_errors(hass: HomeAssistant, search, error) -> None:
    result = await _start_flow(hass, search)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": error}


async def test_config_flow_rejects_duplicates(hass: HomeAssistant) -> None:
    MockConfigEntry(
        domain=DOMAIN, data=ENTRY_DATA, unique_id="3937_10_soltauer str."
    ).add_to_hass(hass)
    result = await _start_flow(hass, AsyncMock(return_value=[STOP]))
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"stop_id": "3937"})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def _setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, data=ENTRY_DATA)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _board(now: datetime) -> list[Departure]:
    """A board with trams planned 8 and 23 minutes from now, the first one 2 minutes late."""
    first = (now + timedelta(minutes=8)).replace(second=0, microsecond=0)
    second = first + timedelta(minutes=15)
    return [
        Departure("10", DIR, first, first + timedelta(minutes=2), False),
        Departure("10", "Halle (Saale), Hauptbahnhof (Tram/Bus)", first, first, False),
        Departure("10", DIR, second, second, False),
    ]


async def test_action_with_offset(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(BOARD, AsyncMock(side_effect=lambda stop, now, duration: _board(now))):
        result = await hass.services.async_call(
            DOMAIN, "get_departure", {"offset_minutes": 8}, blocking=True, return_response=True
        )
    assert result["status"] == "delayed"
    assert result["delay_minutes"] == 2
    assert "2 Minuten verspätet" in result["text"]


async def test_action_without_offset_returns_next_departure(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(BOARD, AsyncMock(side_effect=lambda stop, now, duration: _board(now))):
        result = await hass.services.async_call(
            DOMAIN, "get_departure", {}, blocking=True, return_response=True
        )
    assert result["status"] == "delayed"
    assert result["in_minutes"] in (9, 10)  # planned in 8 min plus 2 min delay
    assert "Abfahrt in" in result["text"]


async def test_action_not_found(hass: HomeAssistant) -> None:
    await _setup(hass)
    with patch(BOARD, AsyncMock(return_value=[])):
        result = await hass.services.async_call(
            DOMAIN, "get_departure", {"offset_minutes": 8}, blocking=True, return_response=True
        )
    assert result["status"] == "not-found"


@pytest.mark.parametrize("error", [aiohttp.ClientError(), TimeoutError(), HafasError("x")])
async def test_action_returns_error_result_instead_of_raising(hass: HomeAssistant, error) -> None:
    await _setup(hass)
    with patch(BOARD, AsyncMock(side_effect=error)):
        result = await hass.services.async_call(
            DOMAIN, "get_departure", {"offset_minutes": 8}, blocking=True, return_response=True
        )
    assert result["status"] == "error"
    assert "nicht erreichbar" in result["text"]


async def test_action_needs_an_entry_id_when_several_lines_are_set_up(hass: HomeAssistant) -> None:
    first = await _setup(hass)
    second = MockConfigEntry(domain=DOMAIN, data={**ENTRY_DATA, "line": "1"}, unique_id="other")
    second.add_to_hass(hass)
    await hass.config_entries.async_setup(second.entry_id)
    with patch(BOARD, AsyncMock(return_value=[])):
        with pytest.raises(ServiceValidationError):
            await hass.services.async_call(
                DOMAIN, "get_departure", {}, blocking=True, return_response=True
            )
        result = await hass.services.async_call(
            DOMAIN,
            "get_departure",
            {"config_entry_id": first.entry_id},
            blocking=True,
            return_response=True,
        )
    assert result["status"] == "not-found"


async def test_action_without_any_entry_raises(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(DOMAIN, "get_departure", {}, blocking=True, return_response=True)


async def test_entry_unloads(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    assert await hass.config_entries.async_unload(entry.entry_id)
