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

from collections.abc import Callable
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

#: The name the serve gave the poster of a hit, and how Home Assistant is asked to
#: fetch it: the entity's own `get_browse_image_url`, so the picture travels the
#: same signed route as the card's one and the browser never talks to the serve.
_POSTER = "poster"
Thumbnail = Callable[[str, str, str], str]

#: What the serve calls a picture's kind, and what Home Assistant calls the same thing.
#: A kind outside this map (`Kind` also allows `"other"`) falls back to plain video.
_MEDIA_CLASS: dict[str, MediaClass] = {"movie": MediaClass.MOVIE, "tv": MediaClass.TV_SHOW}
_MEDIA_TYPE: dict[str, MediaType] = {"movie": MediaType.MOVIE, "tv": MediaType.TVSHOW}

#: `mdi:flash`, verified present (`grep -l`) in nine of the shipped 2026.9.0 frontend
#: bundles on the stand, e.g. `10077.*.js` - but absent from the class-to-icon table
#: the row renderer reads (`6605.*.js`: twenty classes, no lightning among them). A
#: class's icon is Home Assistant's own choice; a shape outside that table can only
#: reach the row as a picture, not as an icon.
_FLASH_PATH = "M7,2V13H10V22L17,10H13L17,2H7Z"

#: `ha-media-browser-thumbnail` draws whatever URL it is given as a plain CSS
#: `background-image`, and skips its own load-and-measure probe outright for anything
#: starting `data:image/svg+xml` (`6605.*.js`, `_probeSize`) - an inline SVG is a
#: destination this component already expects, not one snuck past it. The row's
#: `graphic="medium"` slot is a fixed 56x56 box (`--mdc-list-item-graphic-size`,
#: default `56px`, `23879.*.js`) and the neighbouring `ha-svg-icon` next to it draws
#: at 24x24 (`--mdc-icon-size`, default `24px`, `10077.*.js`). Framing the same 24x24
#: glyph in a 56x56 `viewBox` and centring it there (offset 16 each side) makes
#: `background-size: contain` (`6605.*.js`) place it at that same 24px height instead
#: of blowing it up to fill the box.
#:
#: Known limit: `ha-svg-icon` is recoloured by the theme, a `data:` picture is not -
#: `#8a8a8a` is picked here only for being readable on both a light and a dark
#: background; the owner may want a different one.
_FLASH_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56">'
    f'<g transform="translate(16,16)"><path fill="#8a8a8a" d="{_FLASH_PATH}"/></g>'
    "</svg>"
)
_FLASH_THUMBNAIL = f"data:image/svg+xml,{quote(_FLASH_SVG, safe='')}"


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
    """Empty until searched: a place to type into, not a catalogue to page through.

    A found picture is read by its name, and a tile is too narrow to hold one: the
    grid cut the name off and a person had to hover a tile to learn what it was. The
    frontend takes the layout of what is found from `children_media_class` of the
    node it stands *in*, not from the class of what it found
    (`MediaClassBrowserSettings[e.children_media_class]` of `_currentItem`, shipped
    `55397.*.js`), and left unset it reads `directory`, whose layout is the grid.
    `music` is one of the three classes laid out as a column, and its
    `show_list_images` is what keeps a poster in every found row.

    This node's own icon, seen where it sits inside the root's list, is a separate
    question: the row renderer reads it from the node's *own* `media_class`
    whenever that is not `directory`, ignoring `children_media_class` entirely
    (`EC["directory"===e.media_class&&e.children_media_class||e.media_class].icon`,
    same file) - `directory` here used to hand that read down to `children_media_
    class` instead, which is why this row, standing in a list of two, wore a music
    note - the price of the column, paid where nobody was reading music. `movie`
    closes that hand-me-down and draws a clapperboard instead, while its own
    `show_list_images` is `!0` too, so the poster in a found row does not move.
    """
    return BrowseMedia(
        media_class=MediaClass.MOVIE,
        children_media_class=MediaClass.MUSIC,
        media_content_id=MENU_ID,
        media_content_type=MediaType.VIDEO,
        title=MENU_ID,
        can_play=False,
        can_expand=True,
        can_search=True,
        children=[],
    )


def _instant_node() -> BrowseMedia:
    """A field to command from: no `can_search`, no children, nothing to pick out of.

    No class in the frontend's icon table draws a lightning bolt (`6605.*.js`: twenty
    classes, none of them this one), so the row wears `_FLASH_THUMBNAIL` instead of a
    class-driven icon: a row draws its thumbnail over its icon whenever both the
    node it sits *in* allows pictures and the row itself carries one
    (`_renderListItem`, `55397.*.js`), and the root this row sits in is a plain
    `directory`, which does.
    """
    return BrowseMedia(
        media_class=MediaClass.APP,
        media_content_id=INSTANT_ID,
        media_content_type=MediaType.APP,
        title=INSTANT_TITLE,
        can_play=False,
        can_expand=True,
        thumbnail=_FLASH_THUMBNAIL,
    )


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


__all__ = ["INSTANT_ID", "MENU_ID", "browse", "decode_message", "decode_pick", "search_media"]
