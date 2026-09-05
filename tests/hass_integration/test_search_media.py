"""Ответ поисковой строки: порядок находок, их имена и картинки."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from tests.hass_integration.conftest import BASE, PLAYER, sent, snapshot
from tests.hass_integration.helpers import added, served
from torrcast.domain.facts.fact import Fact
from torrcast.domain.numbered_line import _numbered_line
from torrcast.domain.picture import Picture
from torrcast.usecases.choice.head_line import head_line


async def test_search_media_puts_the_picture_a_bare_play_takes_first(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """One query, one film: `result[0]` is what a bare `POST /api/play` would start.

    Home Assistant's own `MediaSearchAndPlayHandler` plays `result[0]`, so the hit the
    serve flagged `default` has to lead even when the serve lists it second. Everything
    else keeps the serve's order, and every hit keeps its own pick number.

    Searched from the `menu` node - the only field that hands a person a list at all.
    """
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(
        f"{BASE}/api/search",
        json=served(
            [Picture(title="Матрица", year=1999), Picture(title="Чернобыль", year=2019, kind="tv")],
            taken=2,
        ),
    )
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "матрица", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    posted = [call for call in aioclient_mock.mock_calls if call[0] == "POST"]
    assert sent(posted[0]) == {"query": "матрица"}
    hits = answer[PLAYER].result
    assert [hit.title for hit in hits] == [
        "Чернобыль (2019, series) - Russian title only",
        "Матрица (1999) - Russian title only",
    ]
    assert hits[0].media_class == "tv_show"
    assert hits[0].can_play is True
    assert hits[1].media_class == "movie"
    #: The number travels inside the id, so moving a hit up the screen does not renumber it.
    assert hits[0].media_content_id == (
        "torrcast://pick/2?q=%D0%BC%D0%B0%D1%82%D1%80%D0%B8%D1%86%D0%B0"
    )
    assert hits[1].media_content_id == (
        "torrcast://pick/1?q=%D0%BC%D0%B0%D1%82%D1%80%D0%B8%D1%86%D0%B0"
    )


async def test_a_hit_is_named_in_the_tongue_the_product_speaks(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """One stand, one query: the card calls a picture what the menu of `cast` calls it.

    Under `language=en` this list answered in Russian while `cast --menu` of the very
    same serve answered in English: what to call a picture was decided twice, and the
    second place knew nothing of the language the product speaks. It is decided once
    now, by the product, and travels ready in `shown`.

    A picture the product has no English name for keeps its own and is neither blanked
    nor transliterated - a person cannot pick a line that has no name. The raw name
    stays in `title`, because the poster of a hit is looked up by it.

    A picture with no year at all is dated `(?)`, the way the menu of `cast` dates it:
    the year in this list tells two namesakes apart, and a blank where the console
    prints something is the same one query, two answers this test exists about.
    """
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(
        f"{BASE}/api/search",
        json=served(
            [
                Picture(title="Назад в будущее", year=1985, original="Back to the Future"),
                Picture(title="Back To The Future", year=None),
                Picture(
                    title="Экспедиция: Назад в будушее",
                    year=2021,
                    kind="tv",
                    original="Expedition: Back to the Future",
                ),
            ],
            taken=1,
        ),
    )
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "back to the future", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )

    assert [hit.title for hit in answer[PLAYER].result] == [
        "Back to the Future (1985)",
        "Back To The Future (?)",
        "Expedition: Back to the Future (2021, series)",
    ]


async def test_a_series_hit_says_it_is_a_series_and_a_film_hit_says_nothing(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """One query, a series and a film: a person reads which is which off the line.

    The list said nothing at all about a hit's kind while the menu of `cast` on the very
    same stand said it in a word. The kind does travel - `media_class` of a hit is
    `tv_show` - but nobody sees it: the frontend lays this list out by
    `children_media_class` of the node the hits stand in (`menu`, `music`), and every row
    of that layout draws the same note icon whatever the row itself is. So the word has
    to be in the title, and it is written by the product: the mark is a localised phrase
    (`, series` under English, `, сериал` under Russian) and the integration knows nothing
    of the language the serve speaks.

    Both sides are asserted apart. A mark on everything reads no better than a mark on
    nothing, so the film is named too, and by its own assert.
    """
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(
        f"{BASE}/api/search",
        json=served(
            [
                Picture(title="Рэмбо", year=2022, kind="tv", original="Rambo"),
                Picture(title="Рэмбо: Первая кровь", year=1982, original="First Blood"),
            ],
            taken=1,
        ),
    )
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "рэмбо", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    hits = answer[PLAYER].result

    assert hits[0].title == "Rambo (2022, series)", "сериал обязан называть себя сериалом"
    assert hits[1].title == "First Blood (1982)", "у фильма пометки вида нет"


async def test_a_hit_is_titled_the_way_the_console_menu_titles_the_same_picture(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """The line in the card is the line `cast --menu` prints for that picture.

    Not a literal copied into this file: the expected string is asked of
    `head_line`, the very function the console menu prints its item with, so the two
    places cannot drift apart quietly. That drift is the whole defect - the card was
    composing `"{name} ({year})"` with a rule of its own.

    A picture standing under a franchise ruler is compared separately
    (`test_a_picture_under_the_numbered_line_reads_the_same_on_both_sides`): the console
    used to sign it differently, so that case is worth a test of its own.
    """
    pictures = [
        Picture(title="Рэмбо", year=2022, kind="tv", original="Rambo"),
        Picture(title="Рэмбо: Первая кровь", year=1982, original="First Blood"),
        Picture(title="Ёлки", year=2010),
    ]
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}/api/search", json=served(pictures, taken=1))
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "рэмбо", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )

    assert not _numbered_line(pictures)[1], "хвоста линейки в этом наборе нет"

    for picture, hit in zip(pictures, answer[PLAYER].result, strict=True):
        console = head_line(1, picture, Fact()).removeprefix("  1. ")

        assert hit.title == console


async def test_a_picture_under_the_numbered_line_reads_the_same_on_both_sides(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """A picture under the franchise ruler is signed like any other, on both sides.

    The split is alive and asserted, not assumed: `Cars Toons` stands under the numbered
    `Cars`, and that is what decides the order of the menu. The note that used to
    explain the drop is gone from the PRODUCT (owner, 04-09-2026), not moved to the
    other side of the seam: for the query the owner measured it stood on 18 lines out of
    27 on BOTH sides alike, and a note on two thirds of a list reads no better than a
    note on none of it. In the card it had nothing to point at either: no ruler there.

    Two failures go red here at once. Bring the note back into the shared rule and the
    literal console line drifts; bring it back into one side only and the two sides
    drift apart.
    """
    numbered = [
        Picture(title="Тачки", year=2006, part=1, original="Cars"),
        Picture(title="Тачки 2", year=2011, part=2, original="Cars 2"),
    ]
    under = Picture(title="Тачки: Мультачки", year=2008, original="Cars Toons")
    pictures = [*numbered, under]
    await added(hass, aioclient_mock, snapshot())
    aioclient_mock.post(f"{BASE}/api/search", json=served(pictures, taken=1))
    answer = await hass.services.async_call(
        "media_player",
        "search_media",
        {"entity_id": PLAYER, "search_query": "тачки", "media_content_id": "menu"},
        blocking=True,
        return_response=True,
    )
    hits = answer[PLAYER].result

    assert [p.key for p in _numbered_line(pictures)[1]] == [under.key], "пункт стоит под линейкой"
    assert head_line(3, under, Fact()) == "  3. Cars Toons (2008)"

    for number, (picture, hit) in enumerate(zip(pictures, hits, strict=True), start=1):
        assert hit.title == head_line(number, picture, Fact()).removeprefix(f"  {number}. ")
