"""Polls the torrcast serve and carries the commands back to it."""

from __future__ import annotations

import logging
from typing import Any, TypeAlias

import aiohttp
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, PLAYING, SCAN_INTERVAL_IDLE, SCAN_INTERVAL_SHOWING, SHOWING_STATES
from .mark_position import mark_position
from .serve_client import ServeClient

_LOGGER = logging.getLogger(__name__)


class Coordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Holds the last snapshot of the serve and speaks to it on behalf of the entity."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: TorrcastConfigEntry,
        host: str,
        port: int,
        version: str | None,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=SCAN_INTERVAL_IDLE,
        )
        self.base_url = f"http://{host}:{port}"
        #: Version of the integration itself, to be compared with the one of the serve.
        self.integration_version = version
        #: When the bookmark on hand was TAKEN - the point the card counts the slider
        #: from. Deliberately not "when the answer arrived": see
        #: :func:`custom_components.torrcast.mark_position.mark_position`.
        self.position_at = dt_util.utcnow()
        self._position: float | None = None
        self._client = ServeClient(async_get_clientsession(hass), self.base_url)
        self._told_error: str | None = None
        self._told_version = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Asks for the state; a silent serve turns the entity unavailable.

        The log is not spammed on purpose: the base coordinator says the first failure
        out loud and lowers the rest to debug until the serve answers again.
        """
        try:
            snapshot = await self._client.state()
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise UpdateFailed(f"{self.base_url} does not answer: {error}") from error
        self._position, self.position_at = mark_position(
            snapshot.get("position"),
            snapshot.get("state") == PLAYING,
            self._position,
            self.position_at,
            dt_util.utcnow(),
        )
        showing = snapshot.get("state") in SHOWING_STATES
        self.update_interval = SCAN_INTERVAL_SHOWING if showing else SCAN_INTERVAL_IDLE
        self._tell_version(snapshot.get("version"))
        self._tell_error(snapshot.get("last_error"))
        return snapshot

    def _tell_version(self, served: str | None) -> None:
        """Says once that the serve and the integration differ in the major digit."""
        mine = self.integration_version
        if self._told_version or not served or not mine:
            return
        if served.split(".")[0] == mine.split(".")[0]:
            return
        self._told_version = True
        _LOGGER.warning(
            "torrcast serves %s while the integration is %s: the major digits differ",
            served,
            mine,
        )

    def _tell_error(self, last_error: str | None) -> None:
        """Shows a new failure of the serve once, not on every poll of the same text."""
        if not last_error:
            self._told_error = None
            return
        if last_error == self._told_error:
            return
        self._told_error = last_error
        persistent_notification.async_create(
            self.hass,
            last_error,
            title="torrcast",
            notification_id=f"{DOMAIN}_last_error",
        )

    async def async_play(self, query: str, pick: int | None = None) -> None:
        """Asks for a show by the same words a person would type in the terminal."""
        await self._client.play(query, pick)
        await self.async_request_refresh()

    async def async_resume(self) -> None:
        """Asks for the last thing watched again, the way a bare `cast` does."""
        await self._client.resume()
        await self.async_request_refresh()

    async def async_search(self, query: str) -> list[dict[str, Any]]:
        """What the serve would find for the query; nothing is started by asking."""
        return await self._client.search(query)

    async def async_poster(self, name: str) -> tuple[bytes | None, str | None]:
        """The bytes of one hit's poster and its type; nothing found is a bare pair."""
        return await self._client.poster(name)

    async def async_control(self, cmd: str, arg: float | None = None) -> None:
        """Sends one control command; `arg` is absent for `toggle` and `stop`."""
        await self._client.control(cmd, arg)
        await self.async_request_refresh()

    async def async_next(self) -> None:
        """Asks for the next episode of the series on the screen."""
        await self._client.next_episode()
        await self.async_request_refresh()


#: The entry carries its own coordinator, so the two are named together.
#: Псевдоним назван псевдонимом вслух: без Home Assistant в венве `ConfigEntry` для
#: тайпчека - `Any`, а `X = Any[Y]` он читает как переменную, а не как тип, и все
#: подписи, где стоит эта запись, тихо перестают что-либо значить.
TorrcastConfigEntry: TypeAlias = ConfigEntry[Coordinator]
