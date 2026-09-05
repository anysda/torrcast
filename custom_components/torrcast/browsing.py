"""The browse dialog and the search field of the card, as the entity answers them."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaType,
    SearchMedia,
    SearchMediaQuery,
)

from .browse import browse
from .decode_message import decode_message
from .decode_pick import decode_pick
from .search_media import search_media

_LOGGER = logging.getLogger(__name__)


class Browsing(MediaPlayerEntity):
    """Everything a person types or picks; the entity itself is assembled in `player`."""

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a plain query as ever, one exact hit of a prior search, or a typed name.

        `media_id` is the same free text a person would hand `cast` on the terminal,
        unless it names a search hit (`decode_pick`) or carries what a person typed into
        the instant field (`decode_message`); the content type is not looked at in any of
        the three cases, and neither is the `announce` the browse dialog adds to a
        message of its own accord.
        """
        _LOGGER.debug("play %s (type %s, extras %s)", media_id, media_type, kwargs)
        typed = decode_message(media_id)
        if typed is not None:
            await self.coordinator.async_play(typed)
            return
        picked = decode_pick(media_id)
        if picked is None:
            await self.coordinator.async_play(media_id)
            return
        query, pick = picked
        await self.coordinator.async_play(query, pick=pick)

    async def async_browse_media(
        self,
        # The platform contract carries the content type even where the tree does not
        # branch by it (see `browse.py`); dropping the parameter would break the call.
        media_content_type: MediaType | str | None = None,  # noqa: ARG002
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Root, and its one child that carries the search field (see `browse.py`)."""
        return browse(media_content_id)

    async def async_search_media(self, query: SearchMediaQuery) -> SearchMedia:
        """Ask the serve for `query`, the picture a bare `POST /api/play` takes first.

        Which picture that is the serve says with a `default` flag on the hit, and
        `search_media` moves it to the front: Home Assistant's own voice handler plays
        `result[0]`, so first has to mean taken.

        Only the `menu` node carries a search field at all (see `browse.py`), so the
        answer is always that node's full list; a voice command reaching the same place
        without a node of its own gets the same list.

        A blank query is answered with nothing rather than sent on: the serve's own
        `no_query` refusal exists for `/api/play`, not for a search box a person has
        not typed into yet.
        """
        text = query.search_query.strip()
        if not text:
            return search_media(text, [])
        hits = await self.coordinator.async_search(text)
        return search_media(text, hits, self.get_browse_image_url)

    async def async_get_browse_image(
        self,
        # The proxy route carries the hit itself as well as the name of its picture; the
        # name alone is enough here, and dropping the two would break the call.
        media_content_type: MediaType | str,  # noqa: ARG002
        media_content_id: str,  # noqa: ARG002
        media_image_id: str | None = None,
    ) -> tuple[bytes | None, str | None]:
        """The poster of one hit, fetched by Home Assistant itself, never by the browser.

        `get_browse_image_url` (used above) points a hit's thumbnail at Home Assistant's
        own proxy route, which lands here on the server side with the name the serve gave
        the picture in `media_image_id`. So the picture crosses two hops that both already
        exist: browser to Home Assistant, then Home Assistant to the serve on the local
        network - the same pair the card's own picture crosses. Neither hop leaves the
        house, and the query and pick in `media_content_id` are not needed to name a
        picture the serve has already put a name on.
        """
        if not media_image_id:
            return None, None
        fetched: tuple[bytes | None, str | None] = await self.coordinator.async_poster(
            media_image_id
        )
        return fetched
