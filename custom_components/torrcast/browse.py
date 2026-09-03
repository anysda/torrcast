"""Two-level media browser for the entity, and the shape of a picked search hit.

Home Assistant's own frontend only draws a search field once a person has navigated
past the root into a node that answers ``can_search=True`` (seen in the shipped
``27169.*.js`` of Home Assistant 2026.8.1: ``navigateIds.length > 1 && ... &&
t.can_search``). A one-level tree never reaches that condition, so the browser here is
always root -> one of two children, both carrying ``can_search``.

The frontend's own ``_search()`` (same ``27169.*.js``) reads the ``media_content_id``
of the node a person is standing in and hands it straight to the
``media_player/search_media`` websocket command, which lands unchanged in
``SearchMediaQuery.media_content_id`` (``homeassistant/components/media_player/
__init__.py``, ``websocket_search_media``). That is the whole mechanism behind the two
fields below: the node a person searched from is the mode they asked for, and nothing
about it needs to travel any other way.

- **instant** - named and playing, no list: the one hit ``async_search_media`` marks
  ``default`` (the same picture a bare ``cast <query>`` would take, per
  ``enter_take``), and no other.
- **menu** - the same full list a search has always answered with, a person still
  picks by hand.

A found picture travels back through ``async_play_media`` as a plain
``media_content_id`` string, and that string has to survive the round trip, carry both
the query and the number of the pick, and stay readable in a log line. ``torrcast://
pick/<N>?q=<query>`` does all three: the scheme keeps it out of the way of a bare-text
query (still just the words a person would type, unmarked), the path carries the pick
number a human reads at a glance, and the query string carries the words that found it.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaType,
    SearchMedia,
)

#: Scheme and host of a picked search hit; anything else in `media_content_id` is a
#: bare query, exactly as `async_play_media` has always treated it.
_SCHEME = "torrcast"
_PICK_HOST = "pick"

#: The three browse nodes: an empty root and its two searchable children. The titles
#: are the two words the owner asked for, verbatim - a person reads them on the field.
_ROOT_ID = ""
INSTANT_ID = "instant"
MENU_ID = "menu"

#: What the serve calls a picture's kind, and what Home Assistant calls the same thing.
#: A kind outside this map (`Kind` also allows `"other"`) falls back to plain video.
_MEDIA_CLASS: dict[str, MediaClass] = {"movie": MediaClass.MOVIE, "tv": MediaClass.TV_SHOW}
_MEDIA_TYPE: dict[str, MediaType] = {"movie": MediaType.MOVIE, "tv": MediaType.TVSHOW}


def encode_pick(query: str, pick: int) -> str:
    """The `media_content_id` of one result of `query`, numbered `pick`."""
    return f"{_SCHEME}://{_PICK_HOST}/{pick}?q={quote(query, safe='')}"


def decode_pick(media_content_id: str) -> tuple[str, int] | None:
    """The query and pick number a `media_content_id` names; `None` for a bare query."""
    parsed = urlsplit(media_content_id)
    if parsed.scheme != _SCHEME or parsed.netloc != _PICK_HOST:
        return None
    number = parsed.path.lstrip("/")
    if not number.isdigit():
        return None
    query = parse_qs(parsed.query).get("q", [""])[0]
    return query, int(number)


def browse(media_content_id: str | None) -> BrowseMedia:
    """The root, or one of its two searchable children; anything else is not ours."""
    if media_content_id in (None, _ROOT_ID):
        return _root()
    if media_content_id == INSTANT_ID:
        return _search_node(INSTANT_ID)
    if media_content_id == MENU_ID:
        return _search_node(MENU_ID)
    raise BrowseError(f"torrcast does not browse {media_content_id!r}")


def _root() -> BrowseMedia:
    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=_ROOT_ID,
        media_content_type=MediaType.VIDEO,
        title="torrcast",
        can_play=False,
        can_expand=True,
        children=[_search_node(INSTANT_ID), _search_node(MENU_ID)],
    )


def _search_node(node_id: str) -> BrowseMedia:
    """Empty until searched: a place to type into, not a catalogue to page through."""
    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=node_id,
        media_content_type=MediaType.VIDEO,
        title=node_id,
        can_play=False,
        can_expand=True,
        can_search=True,
        children=[],
    )


def search_media(query: str, results: list[dict[str, Any]], *, node_id: str | None) -> SearchMedia:
    """The bridge's `results` list turned into what `async_search_media` answers with.

    The hit the serve flagged `default` goes first, and that flag is the whole contract
    between the two halves: it marks the one picture a bare `POST /api/play` of the same
    query would start, asked of the product itself (`hass/searching.py`). Home Assistant's
    own `MediaSearchAndPlayHandler` plays `result[0]` and nothing else, so a voice command
    and a bare play have to agree there or one query names two different films.

    Nothing else about the order is ours to change, and nothing has to be: the pick number
    a hit plays by travels inside its `media_content_id`, not in its place on the screen.

    `node_id` is the `media_content_id` the frontend's own search box hands back - the
    node a person searched from, and therefore the mode they asked for
    (:data:`INSTANT_ID` or :data:`MENU_ID`). `instant` keeps only the `default` hit;
    anything else, `menu` included, keeps the full ordered list as before.
    """
    ordered = sorted(results, key=lambda result: not result.get("default"))
    if node_id == INSTANT_ID:
        ordered = ordered[:1] if ordered and ordered[0].get("default") else []
    return SearchMedia(result=[_hit(query, result) for result in ordered])


def _hit(query: str, result: dict[str, Any]) -> BrowseMedia:
    kind = str(result.get("kind", ""))
    title = str(result.get("title", ""))
    year = result.get("year")
    return BrowseMedia(
        media_class=_MEDIA_CLASS.get(kind, MediaClass.VIDEO),
        media_content_id=encode_pick(query, int(result["pick"])),
        media_content_type=_MEDIA_TYPE.get(kind, MediaType.VIDEO),
        title=f"{title} ({year})" if year else title,
        can_play=True,
        can_expand=False,
    )


__all__ = ["INSTANT_ID", "MENU_ID", "browse", "decode_pick", "search_media"]
