"""Дерево обзора: корень, узел меню и поле мгновенного ввода."""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote

from homeassistant.core import HomeAssistant

from custom_components.torrcast.browse import _FLASH_PATH
from tests.hass_integration.conftest import PLAYER, snapshot
from tests.hass_integration.helpers import added


async def test_browse_media_root_puts_menu_first_and_instant_second(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """Menu leads, and only menu searches: instant is a field to command from.

    The search field only draws past the root, so each mode needs a child of its own.
    Instant's id is what makes the browse dialog draw a message field with a *Say*
    button instead of a list (`browse.py`), and a node that also answered `can_search`
    would be the very two-step search the owner asked to be rid of.
    """
    await added(hass, aioclient_mock, snapshot())
    root = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER},
        blocking=True,
        return_response=True,
    )
    children = root[PLAYER].children
    #: The owner's own two words, in the order he asked for them.
    assert [child.title for child in children] == ["menu", "instant"]
    assert [child.can_expand for child in children] == [True, True]
    assert [bool(child.can_search) for child in children] == [True, False]
    assert children[1].media_content_id.startswith("media-source://tts/")

    menu = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    #: Empty before a search, but still a legible folder, not a dead end.
    assert menu[PLAYER].children == []
    assert menu[PLAYER].can_search is True

    instant = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": children[1].media_content_id},
        blocking=True,
        return_response=True,
    )
    assert instant[PLAYER].title == "instant"
    assert not instant[PLAYER].can_search


async def test_menu_opens_as_a_column_so_a_found_picture_is_read_and_not_hovered(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """The layout of an open node is its own `children_media_class`, so menu names one.

    Left unset it reads `directory`, and `directory` is a grid of tiles too narrow to
    hold a picture's name: a person had to hover a tile to learn what it was. The
    dialog's own `⋮` switch is no answer, it resets to `auto` on every close. Only
    three of the twenty classes are laid out as a column, and the poster survives the
    column because a row's thumbnail comes from the node's own `media_class`, not
    this one - so swapping `children_media_class` to a grid-laid class (e.g.
    `directory`) is the failure this checks, independently of the entity's own class.
    """
    await added(hass, aioclient_mock, snapshot())
    menu = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": "menu", "media_content_type": "video"},
        blocking=True,
        return_response=True,
    )

    assert menu[PLAYER].children_media_class in ("music", "track", "url")


async def test_menu_wears_a_clapperboard_instead_of_the_note_children_media_class_lent_it(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """The icon a row wears for menu, seen from the root, is menu's *own* class.

    The row renderer reads a directory's icon from `children_media_class` instead of
    its own (`EC["directory"===e.media_class&&e.children_media_class||e.media_class]
    .icon`, `55397.*.js`), which is why a `directory` menu with `children_media_class
    = music` used to draw a music note. `movie` closes that hand-me-down: its own icon
    is a clapperboard, and its `show_list_images` is `!0` too (`6605.*.js`), so the
    poster in a found row does not depend on this choice - `test_menu_opens_as_a_
    column...` above guards that column separately, through `children_media_class`.
    """
    await added(hass, aioclient_mock, snapshot())
    menu = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER, "media_content_id": "menu", "media_content_type": "video"},
        blocking=True,
        return_response=True,
    )

    assert menu[PLAYER].media_class == "movie"


async def test_the_instant_field_wears_a_lightning_picture_the_class_table_has_no_icon_for(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """No class in the frontend's icon table draws a lightning bolt (`6605.*.js`:
    twenty classes, none of them this shape), so the field carries the glyph as a
    picture instead of an icon: a row draws its thumbnail over its icon whenever the
    node the row sits *in* allows pictures and the row itself carries one
    (`_renderListItem`, `55397.*.js`) - root here is a plain `directory`, which does.
    """
    await added(hass, aioclient_mock, snapshot())
    root = await hass.services.async_call(
        "media_player",
        "browse_media",
        {"entity_id": PLAYER},
        blocking=True,
        return_response=True,
    )
    instant = root[PLAYER].children[1]
    assert instant.thumbnail is not None
    assert instant.thumbnail.startswith("data:image/svg+xml,")
    assert _FLASH_PATH in unquote(instant.thumbnail)
