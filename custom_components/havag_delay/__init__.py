"""HAVAG Delay: live delay of a HAVAG (Halle) line for automations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .client import HavagClient
from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_OFFSET_MINUTES,
    CONF_DIRECTION,
    CONF_LINE,
    CONF_STOP_ID,
    DOMAIN,
    SERVICE_GET_DEPARTURE,
    UPCOMING_WINDOW_MINUTES,
)
from .hafas import HafasError, describe_upcoming, select_upcoming

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string,
        vol.Optional(ATTR_OFFSET_MINUTES): vol.All(vol.Coerce(int), vol.Range(min=0, max=120)),
    }
)

ERROR_RESULT = {
    "status": "error",
    "planned": None,
    "actual": None,
    "delay_minutes": None,
    "cancelled": False,
    "text": "Die Fahrplanauskunft ist gerade nicht erreichbar.",
}


def _get_entry(hass: HomeAssistant, entry_id: str | None) -> ConfigEntry:
    entries = hass.config_entries.async_entries(DOMAIN)
    if entry_id is not None:
        for entry in entries:
            if entry.entry_id == entry_id:
                return entry
        raise ServiceValidationError(f"Unknown config entry: {entry_id}")
    if not entries:
        raise ServiceValidationError("HAVAG Delay is not set up")
    if len(entries) > 1:
        raise ServiceValidationError("Several lines are set up, pass config_entry_id")
    return entries[0]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the action."""

    async def handle_get_departure(call: ServiceCall) -> ServiceResponse:
        entry = _get_entry(hass, call.data.get(ATTR_CONFIG_ENTRY_ID))
        line = entry.data[CONF_LINE]
        direction = entry.data.get(CONF_DIRECTION, "")
        offset = call.data.get(ATTR_OFFSET_MINUTES, 0)
        now = datetime.now(timezone.utc)
        client = HavagClient(async_get_clientsession(hass))
        try:
            deps = await client.async_departures(
                entry.data[CONF_STOP_ID], now, offset + UPCOMING_WINDOW_MINUTES
            )
            dep = select_upcoming(
                deps, line=line, direction=direction, now=now, offset_minutes=offset
            )
            return describe_upcoming(dep, line, now)
        except (aiohttp.ClientError, TimeoutError, HafasError) as err:
            # Return a result instead of raising, so the notification still goes out.
            _LOGGER.warning("HAVAG request failed: %s", err)
            return dict(ERROR_RESULT)

    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_DEPARTURE,
        handle_get_departure,
        schema=SERVICE_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Nothing to set up per entry: the action reads the entry data on each call."""
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload an entry."""
    return True
