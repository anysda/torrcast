"""Two-level media browser for the entity: a root and its two children.

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
"""

from __future__ import annotations

from urllib.parse import quote

from homeassistant.components.media_player import (
    BrowseError,
    BrowseMedia,
    MediaClass,
    MediaType,
)

from .const import INSTANT_ID, INSTANT_TITLE, MENU_ID, ROOT_ID

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
#: The glyph has to name its own colour, and that is a measured ceiling rather than a
#: choice: `ha-media-browser-thumbnail` hands what it resolved to
#: `style="background-image:url(...)"` on a plain div (`6605.*.js`, `render`), and a
#: background image is a document of its own. Neither `currentColor` nor any CSS
#: variable of the page reaches inside it, so no picture can follow the theme. The
#: icon it stands next to is an `ha-svg-icon` and takes
#: `--mdc-theme-text-icon-on-background`, which the browser sets to
#: `--secondary-text-color` on its own `ha-list` (`55397.*.js`). The colour named here
#: is therefore that same `--secondary-text-color`, read off the theme in use. Change
#: the theme and the two go out of step again; there is no way to keep them together.
_FLASH_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 56 56">'
    f'<g transform="translate(16,16)"><path fill="#5EF6FF" d="{_FLASH_PATH}"/></g>'
    "</svg>"
)
_FLASH_THUMBNAIL = f"data:image/svg+xml,{quote(_FLASH_SVG, safe='')}"


def browse(media_content_id: str | None) -> BrowseMedia:
    """The root, or one of its two children; anything else is not ours."""
    if media_content_id in (None, ROOT_ID):
        return _root()
    if media_content_id == MENU_ID:
        return _menu_node()
    if media_content_id == INSTANT_ID:
        return _instant_node()
    raise BrowseError(f"torrcast does not browse {media_content_id!r}")


def _root() -> BrowseMedia:
    return BrowseMedia(
        media_class=MediaClass.DIRECTORY,
        media_content_id=ROOT_ID,
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
