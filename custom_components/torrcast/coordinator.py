"""Polls the torrcast serve and carries the commands back to it."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    POSTER_REQUEST_TIMEOUT,
    REQUEST_TIMEOUT,
    SCAN_INTERVAL_IDLE,
    SCAN_INTERVAL_SHOWING,
    SEARCH_REQUEST_TIMEOUT,
    SHOWING_STATES,
)

_LOGGER = logging.getLogger(__name__)

#: What the serve answers with 409 and what a person should read instead of the code.
REFUSALS: dict[str, str] = {
    "busy": "torrcast is already starting a show",
    "nothing_playing": "torrcast has nothing on the screen right now",
    "no_next": "there is no next episode",
    "no_volume": "the receiver did not answer about its volume",
}


class TorrcastCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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
        #: from. Deliberately not "when the answer arrived": see :meth:`_mark_position`.
        self.position_at = dt_util.utcnow()
        self._position: float | None = None
        self._session = async_get_clientsession(hass)
        self._told_error: str | None = None
        self._told_version = False

    async def _async_update_data(self) -> dict[str, Any]:
        """Asks for the state; a silent serve turns the entity unavailable.

        The log is not spammed on purpose: the base coordinator says the first failure
        out loud and lowers the rest to debug until the serve answers again.
        """
        snapshot = await self._get_state()
        self._mark_position(snapshot.get("position"))
        showing = snapshot.get("state") in SHOWING_STATES
        self.update_interval = SCAN_INTERVAL_SHOWING if showing else SCAN_INTERVAL_IDLE
        self._tell_version(snapshot.get("version"))
        self._tell_error(snapshot.get("last_error"))
        return snapshot

    def _mark_position(self, raw: Any) -> None:
        """Moves the slider's origin with the bookmark itself, not with every answer.

        The show writes its bookmark once every ten seconds, the poll asks every five,
        and the card draws `position + (now - position_at)`. Stamping the arrival of
        each answer moved the origin under a bookmark that had not moved, so the
        slider walked forward for five seconds and then fell back to the same place -
        again and again, for the whole show.

        A repeated place is not a new measurement, so the origin stays where it was.
        A place that moved forward moves the origin by exactly as much as the bookmark
        moved: the two circles - the show's and the poll's - drift apart, and sooner or
        later a new place arrives a poll late, which is the very same fall back, only
        rare. Lagging further behind than one poll is not worth it though: a bookmark
        standing longer than that is a show that stopped, and the truth about it is
        worth more than a smooth slider.
        """
        place = None if raw is None else float(raw)
        now = dt_util.utcnow()
        if place is None or self._position is None or place < self._position:
            self._position, self.position_at = place, now
            return
        if place == self._position:
            return
        moved = timedelta(seconds=place - self._position)
        self._position = place
        self.position_at = max(now - SCAN_INTERVAL_SHOWING, min(now, self.position_at + moved))

    async def _get_state(self) -> dict[str, Any]:
        try:
            async with self._session.get(
                f"{self.base_url}/api/state",
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                response.raise_for_status()
                snapshot: dict[str, Any] = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise UpdateFailed(f"{self.base_url} does not answer: {error}") from error
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
        """Asks for a show by the same words a person would type in the terminal.

        ``pick`` names one of the pictures a prior :meth:`async_search` answered with;
        left out, the serve picks the same way `cast query` would on its own.
        """
        body: dict[str, Any] = {"query": query}
        if pick is not None:
            body["pick"] = pick
        await self._post("/api/play", body)

    async def async_search(self, query: str) -> list[dict[str, Any]]:
        """Asks the serve what it would find for the query, without starting a show.

        Returns the bare ``results`` list of the answer; a refusal of the serve raises
        the same readable failure a control command would. A search walks out to the
        indexers, so it waits its own, longer :data:`SEARCH_REQUEST_TIMEOUT` instead of
        the short :data:`REQUEST_TIMEOUT` a state poll is answered in.
        """
        try:
            async with self._session.post(
                f"{self.base_url}/api/search",
                json={"query": query},
                timeout=aiohttp.ClientTimeout(total=SEARCH_REQUEST_TIMEOUT),
            ) as response:
                if response.status == 409:
                    raise HomeAssistantError(await self._refusal(response))
                response.raise_for_status()
                found: dict[str, Any] = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as error:
            raise HomeAssistantError(
                f"{self.base_url} did not answer the search: {error}"
            ) from error
        results = found.get("results")
        return list(results) if isinstance(results, list) else []

    async def async_poster(self, name: str) -> tuple[bytes | None, str | None]:
        """The bytes of one hit's poster and its type; nothing found is a bare pair.

        The picture is asked of the serve, never of the site it came from: the serve
        downloaded it for itself and hands it out on its own route in the local network.
        A hit whose picture is still being looked for answers slowly rather than empty,
        so this waits longer than a state poll does (:data:`POSTER_REQUEST_TIMEOUT`).
        """
        try:
            async with self._session.get(
                f"{self.base_url}/api/poster/{quote(name, safe='')}",
                timeout=aiohttp.ClientTimeout(total=POSTER_REQUEST_TIMEOUT),
            ) as response:
                if response.status != 200:
                    return None, None
                return await response.read(), response.headers.get("Content-Type")
        except (aiohttp.ClientError, TimeoutError):
            return None, None

    async def async_control(self, cmd: str, arg: float | None = None) -> None:
        """Sends one control command; `arg` is absent for `toggle` and `stop`."""
        body: dict[str, Any] = {"cmd": cmd}
        if arg is not None:
            body["arg"] = arg
        await self._post("/api/control", body)

    async def async_next(self) -> None:
        """Asks for the next episode of the series on the screen."""
        await self._post("/api/next", None)

    async def _post(self, path: str, body: dict[str, Any] | None) -> None:
        """Posts a command and turns a refusal of the serve into a readable failure."""
        try:
            async with self._session.post(
                f"{self.base_url}{path}",
                json=body,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
            ) as response:
                if response.status == 409:
                    raise HomeAssistantError(await self._refusal(response))
                response.raise_for_status()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise HomeAssistantError(
                f"{self.base_url} did not take the command: {error}"
            ) from error
        await self.async_request_refresh()

    @staticmethod
    async def _refusal(response: aiohttp.ClientResponse) -> str:
        try:
            payload: dict[str, Any] = await response.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            payload = {}
        named = str(payload.get("error", ""))
        return REFUSALS.get(named, f"torrcast refused the command: {named or 'no reason given'}")


#: The entry carries its own coordinator, so the two are named together.
TorrcastConfigEntry = ConfigEntry[TorrcastCoordinator]
