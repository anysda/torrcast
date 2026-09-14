"""Короткое имя и соседи по слову: «Вверх» не встаёт картиной «Шары вверх».

Живой стенд CT501 :8484, 14-09-2026, холодный экземпляр: из индексеров ответил один
Knaben, 24 строки по «Вверх» и ни одной «Вверх / Up (2009)». Поиск по слову взял
«Шары вверх» (2026), добор по «Up» от справки отвергнут счётом картин, и человек
получал карточку чужого фильма. Строки ниже взяты из той выдачи.
"""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._word_neighbours import _asked_in, _neighbours_only
from torrcast.usecases.discover.search_circle import search_circle

_CONFIG = Config(prowlarr_apikey="KEY")

_UP_KNABEN = [
    row(
        "Шары вверх / Balls Up [2026, США, комедия, боевик, WEB-DL-AVC] MVO + Sub", "a", seeders=228
    ),
    row(
        "Шары вверх / Balls Up [2026, США, комедия, боевик, WEB-DL 1080p] MVO + Sub",
        "b",
        seeders=98,
    ),
    row("Вверх по течению / Up The Creek [1984, США, Молодежная комедия, BDRip] 3 VO", "c"),
    row("Жизнь вверх ногами / Life Upside Down [2023, США, комедия, WEB-DL 1080p] Dub", "d"),
    row("Вверх по лестнице, ведущей вниз / Up the Down Staircase [1967, США, драма, DVDRip]", "e"),
    row("Вверх и вниз по лестнице / Upstairs and Downstairs [1959, Великобритания, DVDRip]", "f"),
]
_UP_LATIN = [
    row("Не смотрите наверх / Don't Look Up (2021) WEB-DL [H.264/1080p]", "g", seeders=569),
    row("Не смотрите наверх / Don't Look Up (2021) WEB-DL [H.265/2160p]", "h", seeders=40),
    row("Руки Вверх! (2024) WEBRip [H.264/1080p]", "i", seeders=382),
    row("Супермен 2 / Superman II (1980) BDRip 1080p", "j"),
    row("Шары вверх / Balls Up (2026) WEB-DL 1080p", "k", seeders=120),
    row("Living It Up (1954) 1080p BluRay", "l"),
]
_UP_ITSELF = [
    row("Вверх / Up (2009) BDRip 1080p | D", "m", seeders=32),
    row("Вверх / Up (2009) BDRip-HEVC 1080p от HEVC-CLUB | Лицензия", "n", seeders=7),
]


def _menu(answers: dict[str, list[RawResult]], query: str, about: Origin) -> list[tuple[str, int]]:
    wire_catalogue(about)
    plans = search_circle(
        _CONFIG,
        Args(query=[query]),
        Said(),
        indexer=lambda *_a, **_k: Indexer(answers=answers),
        passport=lambda *_a, **_k: about,
    )
    return [(plan.picture.title, plan.picture.year or 0) for plan in plans]


_UP = Origin(title="Up", year=2009, name="Вверх")


def test_a_poor_listing_without_the_picture_is_not_found_not_a_neighbour() -> None:
    """Картины в выдаче нет вовсе: честное «не найдено», а не «Шары вверх» 2026."""
    with pytest.raises(NotFoundError):
        _menu({"вверх": _UP_KNABEN, "up": _UP_LATIN}, "Вверх", _UP)


def test_the_top_up_by_the_wiki_name_brings_the_picture_past_its_neighbours() -> None:
    """Добор по «Up» привёз и саму картину: она и встаёт, а не соседи и не отказ."""
    menu = _menu({"вверх": _UP_KNABEN, "up": _UP_LATIN + _UP_ITSELF}, "Вверх", _UP)

    assert menu == [("Вверх", 2009)]


def test_a_rich_listing_keeps_the_picture_as_it_was() -> None:
    """Выдача с самой картиной: ответ прежний, раздачи те же."""
    menu = _menu({"вверх": _UP_KNABEN + _UP_ITSELF, "up": _UP_LATIN}, "Вверх", _UP)

    assert menu[0] == ("Вверх", 2009)
    assert ("Шары вверх", 2026) not in menu


def test_several_neighbours_still_send_the_top_up_by_name_and_year() -> None:
    """Живой CT501 :8495: одни «Руки вверх» по-русски, и добор идёт строкой «Вверх 2009».

    Соседи отвечать не вправе, но спросить точнее они по-прежнему велят: латинский «Up»
    тонет в тёзках, а русская строка с годом приносит саму картину с озвучками.
    """
    hands = [
        row("Руки Вверх! (2024) WEBRip [H.264/1080p]", "a", seeders=382),
        row("Руки вверх (1981) DVDRip | P", "b"),
        row("Руки вверх, или Грабители-неудачники / The Curse of Inferno (1996) DVDRip", "c"),
    ]
    wire_catalogue(_UP)
    client = Indexer(answers={"вверх": hands, "вверх 2009": _UP_ITSELF, "up": _UP_LATIN})

    plans = search_circle(
        _CONFIG,
        Args(query=["Вверх"]),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: _UP,
    )

    assert [(plan.picture.title, plan.picture.year) for plan in plans] == [("Вверх", 2009)]
    assert client.asked[-1] == "Вверх 2009"


#: Короткое русское имя, оригинал по карте имён и сосед, у которого это слово внутри.
_CLASS = [
    (
        "Она",
        Origin(title="Her", year=2013, name="Она"),
        [row("Она написала убийство / Murder, She Wrote [1984, США, детектив, DVDRip] MVO", "a")],
        [row("Her Smell (2018) 1080p WEB-DL", "b"), row("Her Story (2016) 1080p WEB-DL", "c")],
        [row("Она / Her (2013) BDRip 1080p | D", "d", seeders=40)],
    ),
    (
        "Мы",
        Origin(title="Us", year=2019, name="Мы"),
        [row("Мы из будущего (2008) DVDRip | Лицензия", "a")],
        [row("Among Us (2021) 1080p WEB-DL", "b"), row("This Is Us (2016) S01 1080p", "c")],
        [row("Мы / Us (2019) BDRip 1080p | D", "d", seeders=40)],
    ),
    (
        "Оно",
        Origin(title="It", year=2017, name="Оно"),
        [row("Оно живое / It's Alive [1974, США, ужасы, DVDRip] AVO", "a")],
        [row("It Follows (2014) 1080p BluRay", "b"), row("It's Alive (1974) 1080p BluRay", "c")],
        [row("Оно / It (2017) BDRip 1080p | D", "d", seeders=40)],
    ),
]


@pytest.mark.parametrize(("query", "about", "ru", "latin", "itself"), _CLASS)
def test_a_short_name_never_stands_as_its_word_neighbour(
    query: str,
    about: Origin,
    ru: list[RawResult],
    latin: list[RawResult],
    itself: list[RawResult],
) -> None:
    """Сосед по слову не отвечает на короткое имя ни без картины, ни рядом с ней."""
    answers = {query.casefold(): ru, about.title.casefold(): latin}
    with pytest.raises(NotFoundError):
        _menu(answers, query, about)

    answers[about.title.casefold()] = latin + itself
    assert _menu(answers, query, about) == [(query, about.year)]


def _picture(title: str, year: int | None, original: str | None = None) -> Picture:
    return Picture(title=title, year=year, kind="movie", original=original)


def test_the_rule_drops_neighbours_and_keeps_the_franchise_of_the_name() -> None:
    """Сосед уходит, часть франшизы остаётся: «Тачки 2» тоже называется «Тачки»."""
    cars = Origin(title="Cars", year=2006, name="Тачки")
    found = [
        _picture("Тачки", 2006, "Cars"),
        _picture("Тачки 2", 2011),
        _picture("Мультачки", 2008),
    ]

    assert [p.title for p in _neighbours_only(found, "тачки", cars)] == ["Тачки", "Тачки 2"]
    assert _neighbours_only([_picture("Шары вверх", 2026, "Balls Up")], "вверх", _UP) == []


def test_a_picture_without_the_word_in_its_names_is_no_neighbour() -> None:
    """Живой CT501 :8495: «Грязные игры / Game of Love (Dirty Games)» 2021 при справке 2005.

    Имя «Dirty Games» стоит у раздачи в скобках, разбор его не сохранил, и слова запроса в
    именах картины нет. Сосед по слову - тот, у кого оно есть, эту картину резать нечем.
    """
    about = Origin(title="Dirty Games", year=2005, name="Dirty Games")
    alias = _picture("Грязные игры", 2021, "Game of Love")
    found = [_picture("Грязные игры", 1989, "Dirty Games"), alias, _picture("Dirty Games", 2026)]

    assert alias in _neighbours_only(found, "Dirty Games", about)
    assert _neighbours_only([alias], "Dirty Games", about) == [alias]
    kitchen = _picture("Dirty Games in the Kitchen", 2023)
    assert _neighbours_only([alias, kitchen], "Dirty Games", about) == [alias]


def test_the_rule_is_silent_without_the_word_of_the_wiki() -> None:
    """Нет года, оригинала или имя лишь похоже: отличить соседа нечем, найденное как было."""
    found = [_picture("Шары вверх", 2026, "Balls Up")]

    assert _neighbours_only(found, "вверх", Origin(title="Up")) == found
    assert _neighbours_only(found, "вверх", Origin(year=2009, name="Вверх")) == found
    assert _neighbours_only(found, "вверх", Origin(title="Up", year=2009, guessed=True)) == found


def test_a_partial_name_keeps_its_pictures_by_the_year_of_the_wiki() -> None:
    """«Гарри Поттер» своих частей не подписывает, а год первой части у них есть."""
    potter = Origin(title="Harry Potter", year=2001, name="Гарри Поттер")
    found = [
        _picture("Гарри Поттер и философский камень", 2001),
        _picture("Гарри Поттер и тайная комната", 2002),
        _picture("Гарри Поттер и узник Азкабана", 2004),
    ]

    assert _neighbours_only(found, "гарри поттер", potter) == found


def test_the_wide_take_is_only_for_an_empty_russian_answer_without_a_part_number() -> None:
    """Картина справки из широкого круга - только когда своего нет и номера части нет."""
    wide = [_picture("Руки вверх", 2024), _picture("Вверх", 2009, "Up"), _picture("Up", 2026)]

    assert [p.year for p in _asked_in([], wide, "вверх", None, _UP)] == [2009]
    assert _asked_in([wide[0]], wide, "вверх", None, _UP) == []
    assert _asked_in([], wide, "вверх", 2, _UP) == []
