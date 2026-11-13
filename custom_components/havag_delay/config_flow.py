"""Config flow for HAVAG Delay."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .client import HavagClient
from .const import (
    CONF_DIRECTION,
    CONF_LINE,
    CONF_STOP_ID,
    CONF_STOP_NAME,
    CONF_STOP_QUERY,
    DOMAIN,
)
from .hafas import HafasError


class HavagDelayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Search a stop, pick it, enter line and direction."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}
        self._stops: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            client = HavagClient(async_get_clientsession(self.hass))
            try:
                stops = await client.async_search_stops(user_input[CONF_STOP_QUERY])
            except (aiohttp.ClientError, TimeoutError, HafasError):
                errors["base"] = "cannot_connect"
            else:
                if not stops:
                    errors["base"] = "no_results"
                else:
                    self._user_input = user_input
                    self._stops = {stop.id: stop.name for stop in stops}
                    return await self.async_step_pick_stop()

        schema = vol.Schema(
            {
                vol.Required(CONF_STOP_QUERY, default=(user_input or {}).get(CONF_STOP_QUERY, "")): str,
                vol.Required(CONF_LINE, default=(user_input or {}).get(CONF_LINE, "")): str,
                vol.Optional(CONF_DIRECTION, default=(user_input or {}).get(CONF_DIRECTION, "")): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_pick_stop(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            stop_id = user_input[CONF_STOP_ID]
            line = self._user_input[CONF_LINE].strip()
            direction = self._user_input.get(CONF_DIRECTION, "").strip()
            await self.async_set_unique_id(f"{stop_id}_{line}_{direction.lower()}")
            self._abort_if_unique_id_configured()
            stop_name = self._stops[stop_id]
            title = f"Linie {line} · {stop_name}"
            if direction:
                title += f" → {direction}"
            return self.async_create_entry(
                title=title,
                data={
                    CONF_STOP_ID: stop_id,
                    CONF_STOP_NAME: stop_name,
                    CONF_LINE: line,
                    CONF_DIRECTION: direction,
                },
            )

        schema = vol.Schema(
            {
                vol.Required(CONF_STOP_ID): SelectSelector(
                    SelectSelectorConfig(
                        options=[SelectOptionDict(value=k, label=v) for k, v in self._stops.items()],
                        mode=SelectSelectorMode.LIST,
                    )
                )
            }
        )
        return self.async_show_form(step_id="pick_stop", data_schema=schema)
