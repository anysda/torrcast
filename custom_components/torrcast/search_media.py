"""The serve's list of found pictures turned into what the search field answers with."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.components.media_player import (
    BrowseMedia,
    MediaClass,
    MediaType,
    SearchMedia,
)

from .encode_pick import encode_pick

#: The name the serve gave the poster of a hit, and how Home Assistant is asked to
#: fetch it: the entity's own `get_browse_image_url`, so the picture travels the
#: same signed route as the card's one and the browser never talks to the serve.
_POSTER = "poster"
Thumbnail = Callable[[str, str, str], str]

#: What the serve calls a picture's kind, and what Home Assistant calls the same thing.
#: A kind outside this map (`Kind` also allows `"other"`) falls back to plain video.
_MEDIA_CLASS: dict[str, MediaClass] = {"movie": MediaClass.MOVIE, "tv": MediaClass.TV_SHOW}
_MEDIA_TYPE: dict[str, MediaType] = {"movie": MediaType.MOVIE, "tv": MediaType.TVSHOW}


def search_media(
    query: str, results: list[dict[str, Any]], thumbnail: Thumbnail | None = None
) -> SearchMedia:
    """The bridge's `results` list turned into what `async_search_media` answers with.

    The hit the serve flagged `default` goes first, and that flag is the whole contract
    between the two halves: it marks the one picture a bare `POST /api/play` of the same
    query would start, asked of the product itself (`hass/searching.py`). Home Assistant's
    own `MediaSearchAndPlayHandler` plays `result[0]`, so a voice command and a bare play
    have to agree there or one query names two different films.

    Nothing else about the order is ours to change, and nothing has to be: the pick number
    a hit plays by travels inside its `media_content_id`, not in its place on the screen.

    `thumbnail` builds the address a poster is fetched from; a hit the serve has no
    picture for keeps none, and stays a plain line rather than a frame around nothing.
    """
    ordered = sorted(results, key=lambda result: not result.get("default"))
    return SearchMedia(result=[_hit(query, result, thumbnail) for result in ordered])


def _hit(query: str, result: dict[str, Any], thumbnail: Thumbnail | None) -> BrowseMedia:
    kind = str(result.get("kind", ""))
    #: The whole line a person reads is written by the product, not composed here: the
    #: serve sends it decided (`hass/search_results.py`), marks and all, and the
    #: integration knows nothing of the language the product speaks - a kind mark reads
    #: `, series` or `, сериал` depending on it. Composing the line here is what let this
    #: list say nothing about a hit being a series while the menu of `cast` on the same
    #: stand said it in words: two places writing one line is two rules.
    #:
    #: `shown` and then `title` are the older contracts of a serve that predates `named`,
    #: read the same way the card falls back from `shown_as` to `title`. With them the
    #: year is glued on here, exactly as it was before - an old serve is not dropped.
    named = str(result.get("named") or "")
    shown = str(result.get("shown") or result.get("title", ""))
    year = result.get("year")
    poster = result.get(_POSTER)
    media_content_id = encode_pick(query, int(result["pick"]))
    media_content_type = _MEDIA_TYPE.get(kind, MediaType.VIDEO)
    return BrowseMedia(
        media_class=_MEDIA_CLASS.get(kind, MediaClass.VIDEO),
        media_content_id=media_content_id,
        media_content_type=media_content_type,
        title=named or (f"{shown} ({year})" if year else shown),
        can_play=True,
        can_expand=False,
        thumbnail=(
            thumbnail(media_content_type, media_content_id, str(poster))
            if thumbnail is not None and poster
            else None
        ),
    )
