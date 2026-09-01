"""Зеркально проверяет строку о занятом телевизоре."""

import pytest

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.entry import Entry
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.say_showing import _say_showing


def test_nothing_is_said_when_nothing_plays(capsys: pytest.CaptureFixture[str]) -> None:
    _say_showing(None)

    assert capsys.readouterr().out == ""


@pytest.mark.usefixtures("_russian_product")
def test_the_viewer_hears_what_will_be_interrupted(capsys: pytest.CaptureFixture[str]) -> None:
    entry = Entry(title="Моана 2", magnet="magnet:?x=1", pos=660.0, dur=5978.0)

    _say_showing(("ключ", entry))

    printed = capsys.readouterr().out
    where = f" {phrase('showing.at', pos='0:11:00')}"
    what = phrase("choice.quoted", it="Моана 2")
    assert phrase("showing.busy", what=what, where=where) in printed


@pytest.mark.usefixtures("_english")
def test_the_interrupted_show_is_named_from_the_reference_cache(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Под EN имя играющей картины - английское, из кэша справки, а не записанное русское."""
    entry = Entry(title="Моана 2", magnet="magnet:?x=1", pos=660.0, dur=5978.0)

    _say_showing(("ключ", entry), origin=lambda title, series: Origin(title="Moana 2"))

    printed = capsys.readouterr().out
    where = f" {phrase('showing.at', pos='0:11:00')}"
    what = phrase("choice.quoted", it="Moana 2")
    assert phrase("showing.busy", what=what, where=where) in printed


@pytest.mark.usefixtures("_english")
def test_a_cache_miss_leaves_the_recorded_name(capsys: pytest.CaptureFixture[str]) -> None:
    """Кэш молчит - показывается записанное имя: честная строка лучше выдуманной."""
    entry = Entry(title="Сваты", magnet="magnet:?x=1", pos=660.0, dur=5978.0)

    _say_showing(("ключ", entry), origin=lambda title, series: None)

    printed = capsys.readouterr().out
    where = f" {phrase('showing.at', pos='0:11:00')}"
    what = phrase("choice.quoted", it="Сваты")
    assert phrase("showing.busy", what=what, where=where) in printed


@pytest.mark.usefixtures("_english")
def test_a_native_picture_keeps_its_recorded_name(capsys: pytest.CaptureFixture[str]) -> None:
    """Английского имени у картины нет вовсе - транслитом его не подменяют."""
    entry = Entry(title="Сваты", magnet="magnet:?x=1", pos=660.0, dur=5978.0)

    _say_showing(("ключ", entry), origin=lambda title, series: Origin(name="Сваты", native=True))

    printed = capsys.readouterr().out
    where = f" {phrase('showing.at', pos='0:11:00')}"
    what = phrase("choice.quoted", it="Сваты")
    assert phrase("showing.busy", what=what, where=where) in printed


@pytest.mark.usefixtures("_russian_product")
def test_the_russian_product_does_not_consult_the_cache(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Под RU строка звучит дословно как была: записанное имя и кавычки русского набора."""
    entry = Entry(title="Моана 2", magnet="magnet:?x=1", pos=660.0, dur=5978.0)

    def forbidden(title: str, series: bool | None) -> Origin | None:
        raise AssertionError("русской строке кэш справки не нужен")

    _say_showing(("ключ", entry), origin=forbidden)

    printed = capsys.readouterr().out
    where = f" {phrase('showing.at', pos='0:11:00')}"
    assert phrase("showing.busy", what="«Моана 2»", where=where) in printed
