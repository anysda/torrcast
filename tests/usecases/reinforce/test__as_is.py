"""Выдача, когда добора не было: год справки спорит с каталогом, но не отнимает."""

from __future__ import annotations

from tests.usecases.reinforce.stand import Said, franchise, row
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.reinforce._as_is import _as_is

#: Живой случай: справка знает «Крестьян» 1935 года, а в каталоге картина 2023-го.
_ROWS = [row("Крестьяне / Chlopi (2023) BDRip 1080p", "a", seeders=40)]


def test_the_year_gate_never_takes_away_what_was_found() -> None:
    """🔴 Живой BDRip выбрасывался целиком, и человек читал «ничего не нашлось».

    Спорить о годе можно, только пока есть о чём спорить: после отказа человеку не
    остаётся вообще ничего.
    """
    found = franchise("крестьяне", _ROWS)
    said = Said()

    _raw, _pictures, stays = _as_is(_ROWS, found, Origin(year=1935), said)

    assert [picture.title for picture in stays] == ["Крестьяне"]
    assert "в каталоге лежит картина 2023 года, а не 1935 - другой там нет" in said.text


def test_the_pictures_are_rebuilt_from_the_catalogue_rows() -> None:
    """Второй список - это картины всей выдачи, а не только найденные запросом."""
    rows = [*_ROWS, row("Другое / Other (2001) BDRip 1080p", "b")]
    found = franchise("крестьяне", rows)

    _raw, pictures, stays = _as_is(rows, found, Origin(), Said())

    assert sorted(picture.title for picture in pictures) == ["Другое", "Крестьяне"]
    assert stays is found, "найденное запросом остаётся тем же списком"


def test_a_year_apart_is_not_a_dispute() -> None:
    """Год проката против года производства: ругаться на ±1 значит ругаться зря."""
    said = Said()

    _as_is(_ROWS, franchise("крестьяне", _ROWS), Origin(year=2022), said)

    assert said.notes == []


def test_a_remake_of_the_same_original_is_not_another_picture() -> None:
    """Справка знает «Fruits Basket» 2006, у индексеров ремейк 2019 - вещь одна и та же."""
    rows = [row("Корзинка фруктов / Fruits Basket (2019) BDRip 1080p", "c")]
    said = Said()

    _as_is(
        rows, franchise("корзинка фруктов", rows), Origin(title="Fruits Basket", year=2006), said
    )

    assert said.notes == []


def test_a_crowd_of_pictures_keeps_silent() -> None:
    """Строка говорится про ОДНУ картину: во франшизе справка отвечает про первую часть."""
    rows = [
        row("Моана / Moana (2016) BDRip 1080p", "d"),
        row("Моана 2 / Moana 2 (2024) BDRip 1080p", "e"),
    ]
    said = Said()

    _as_is(rows, franchise("моана", rows), Origin(year=2016), said)

    assert said.notes == []


def test_the_picture_named_by_the_passport_is_marked_as_its_own() -> None:
    """Русское имя справки - это имя картины, а не совпадение: меню обязано его знать."""
    found = franchise("крестьяне", _ROWS)

    _as_is(_ROWS, found, Origin(name="Крестьяне", native=True), Said())

    assert found[0].native
