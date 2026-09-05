"""Every question and every command the integration puts to the serve over HTTP."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import aiohttp
from homeassistant.exceptions import HomeAssistantError

from .const import POSTER_REQUEST_TIMEOUT, REQUEST_TIMEOUT, SEARCH_REQUEST_TIMEOUT

#: What the serve answers with 409 and what a person should read instead of the code.
REFUSALS: dict[str, str] = {
    "busy": "torrcast is already starting a show",
    "nothing_playing": "torrcast has nothing on the screen right now",
    "no_next": "there is no next episode",
    "no_volume": "the receiver did not answer about its volume",
}


class ServeClient:
    """Talks to one serve; nothing here knows about Home Assistant's own machinery."""

    def __init__(self, session: aiohttp.ClientSession, base_url: str) -> None:
        self.base_url = base_url
        self._session = session

    async def state(self) -> dict[str, Any]:
        """The snapshot of the serve; a silent serve is an error, not an empty answer."""
        async with self._session.get(
            f"{self.base_url}/api/state",
            timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
        ) as response:
            response.raise_for_status()
            snapshot: dict[str, Any] = await response.json(content_type=None)
        return snapshot

    async def play(self, query: str, pick: int | None = None) -> None:
        """Asks for a show by the same words a person would type in the terminal.

        ``pick`` names one of the pictures a prior :meth:`search` answered with; left
        out, the serve picks the same way `cast query` would on its own.
        """
        body: dict[str, Any] = {"query": query}
        if pick is not None:
            body["pick"] = pick
        await self._post("/api/play", body)

    async def resume(self) -> None:
        """Asks for the last thing watched again, the way a bare `cast` does.

        No words go out with it. `/api/play` is the road of a show asked for by name and
        still turns an empty query down; this is the other question, and the answer to it
        - which picture, and which second to carry on from - stays the product's, given
        once for the terminal, the bot and the card alike.
        """
        await self._post("/api/resume", None)

    async def search(self, query: str) -> list[dict[str, Any]]:
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

    async def poster(self, name: str) -> tuple[bytes | None, str | None]:
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

    async def control(self, cmd: str, arg: float | None = None) -> None:
        """Sends one control command; `arg` is absent for `toggle` and `stop`."""
        body: dict[str, Any] = {"cmd": cmd}
        if arg is not None:
            body["arg"] = arg
        await self._post("/api/control", body)

    async def next_episode(self) -> None:
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

    @staticmethod
    async def _refusal(response: aiohttp.ClientResponse) -> str:
        try:
            payload: dict[str, Any] = await response.json(content_type=None)
        except (aiohttp.ClientError, ValueError):
            payload = {}
        named = str(payload.get("error", ""))
        return REFUSALS.get(named, f"torrcast refused the command: {named or 'no reason given'}")
