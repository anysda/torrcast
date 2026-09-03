"""Two-level media browser for the entity, and the shape of a picked search hit.

Home Assistant's own frontend only draws a search field once a person has navigated
past the root into a node that answers ``can_search=True`` (seen in the shipped
``27169.*.js`` of Home Assistant 2026.8.1: ``navigateIds.length > 1 && ... &&
t.can_search``). A one-level tree never reaches that condition, so the browser here is
always root -> one of two children.

- **menu** - the search field: the full list a search has always answered with, a
  person still picks by hand. The node a person searched from arrives in the frontend's
  own ``_search()`` as ``SearchMediaQuery.media_content_id``, so it needs no route of
  its own.
- **instant** - named and playing, no list at all. It carries no ``can_search``: the
  browse dialog draws a message field and a *Say* button for any node whose
  ``media_content_id`` begins with ``media-source://tts/`` (shipped ``55397.*.js``:
  ``isTTSMediaSource(item.media_content_id)`` renders ``<ha-browse-media-tts>`` instead
  of the children list). What a person types comes straight back as a play of
  ``<node id>?message=<text>``, so the field is a command, not a question to a
  catalogue - the same way the Yandex Station integration turns its own two fields into
  a spoken phrase and a command.

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

#: The three browse nodes: an empty root and its two children, menu first. The titles
#: are the two words the owner asked for, verbatim - a person reads them on the field.
#: Only the prefix of the instant id is Home Assistant's; the word past it is ours and
#: comes back untouched.
_ROOT_ID = ""
MENU_ID = "menu"
INSTANT_TITLE = "instant"
INSTANT_ID = f"media-source://tts/{INSTANT_TITLE}"

#: Where the dialog puts what a person typed before handing the id back for playing.
_MESSAGE = "message"

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


def decode_message(media_content_id: str) -> str | None:
    """What a person typed into the instant field; `None` if it came from elsewhere.

    The dialog plays the node's own id with the typed words appended as `message`
    (`_ttsClicked` in the shipped `55397.*.js`), so the words arrive here as a query
    string and nothing else about the id changes.
    """
    node_id, _, typed = media_content_id.partition("?")
    if node_id != INSTANT_ID:
        return None
    return parse_qs(typed).get(_MESSAGE, [""])[0].strip()


def browse(media_content_id: str | None) -> BrowseMedia:
    """The root, or one of its two children; anything else is not ours."""
    if media_content_id in (None, _ROOT_ID):
        return _root()
    if media_content_id == MENU_ID:
        return _menu_node()
    if media_content_id == INSTANT_ID:
        return _instant_node()
    raise BrowseError(f"torrcast does not browse {media_content_id!r}")


def _root() -> BrowseMedia:
    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=_ROOT_ID,
        media_content_type=MediaType.VIDEO,
        title="torrcast",
        can_play=False,
        can_expand=True,
        children=[_menu_node(), _instant_node()],
    )


def _menu_node() -> BrowseMedia:
    """Empty until searched: a place to type into, not a catalogue to page through."""
    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=MENU_ID,
        media_content_type=MediaType.VIDEO,
        title=MENU_ID,
        can_play=False,
        can_expand=True,
        can_search=True,
        children=[],
    )


def _instant_node() -> BrowseMedia:
    """A field to command from: no `can_search`, no children, nothing to pick out of."""
    return BrowseMedia(
        media_class=MediaClass.APP,
        media_content_id=INSTANT_ID,
        media_content_type=MediaType.APP,
        title=INSTANT_TITLE,
        can_play=False,
        can_expand=True,
    )


def search_media(query: str, results: list[dict[str, Any]]) -> SearchMedia:
    """The bridge's `results` list turned into what `async_search_media` answers with.

    The hit the serve flagged `default` goes first, and that flag is the whole contract
    between the two halves: it marks the one picture a bare `POST /api/play` of the same
    query would start, asked of the product itself (`hass/searching.py`). Home Assistant's
    own `MediaSearchAndPlayHandler` plays `result[0]`, so a voice command and a bare play
    have to agree there or one query names two different films.

    Nothing else about the order is ours to change, and nothing has to be: the pick number
    a hit plays by travels inside its `media_content_id`, not in its place on the screen.
    """
    ordered = sorted(results, key=lambda result: not result.get("default"))
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


__all__ = ["INSTANT_ID", "MENU_ID", "browse", "decode_message", "decode_pick", "search_media"]
