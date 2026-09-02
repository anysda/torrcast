"""Finds torrcast over mDNS and lets the address be typed in when it does not."""

from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .const import DEFAULT_PORT, DOMAIN, REQUEST_TIMEOUT

MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
    }
)


class TorrcastConfigFlow(ConfigFlow, domain=DOMAIN):
    """Both ways in end the same: the serve is asked for its state before it is written."""

    VERSION = 1

    def __init__(self) -> None:
        self._host = ""
        self._port = DEFAULT_PORT
        self._tv = "torrcast"

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The address by hand: the fallback for a network that eats multicast."""
        errors: dict[str, str] = {}
        if user_input is not None:
            host = str(user_input[CONF_HOST])
            port = int(user_input.get(CONF_PORT, DEFAULT_PORT))
            snapshot = await self._ask(host, port)
            if snapshot is None:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(f"{host}:{port}")
                self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
                return self._write(host, port, str(snapshot.get("tv") or "torrcast"))
        return self.async_show_form(step_id="user", data_schema=MANUAL_SCHEMA, errors=errors)

    async def async_step_zeroconf(self, discovery_info: ZeroconfServiceInfo) -> ConfigFlowResult:
        """The serve announces itself; a moved address is written over the old one."""
        host = str(discovery_info.host)
        port = discovery_info.port or DEFAULT_PORT
        await self.async_set_unique_id(f"{host}:{port}")
        self._abort_if_unique_id_configured(updates={CONF_HOST: host, CONF_PORT: port})
        snapshot = await self._ask(host, port)
        if snapshot is None:
            return self.async_abort(reason="cannot_connect")
        announced = discovery_info.properties.get("tv") or snapshot.get("tv")
        self._host, self._port = host, port
        self._tv = str(announced or "torrcast")
        self.context["title_placeholders"] = {"name": self._title()}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Nothing is added behind a person's back: the found box is confirmed by hand."""
        if user_input is None:
            return self.async_show_form(
                step_id="zeroconf_confirm",
                description_placeholders={"name": self._title()},
            )
        return self._write(self._host, self._port, self._tv)

    def _title(self) -> str:
        return f"torrcast ({self._tv})"

    def _write(self, host: str, port: int, tv: str) -> ConfigFlowResult:
        self._tv = tv
        return self.async_create_entry(title=self._title(), data={CONF_HOST: host, CONF_PORT: port})

    async def _ask(self, host: str, port: int) -> dict[str, Any] | None:
        """The state of the serve, or ``None`` when it did not answer at all."""
        session = async_get_clientsession(self.hass)
        try:
            async with session.get(
                f"http://{host}:{port}/api/state",
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                response.raise_for_status()
                snapshot: dict[str, Any] = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return None
        return snapshot
