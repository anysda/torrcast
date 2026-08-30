"""Зеркально проверяет строку о занятом телевизоре."""

import pytest

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.entry import Entry
from torrcast.usecases.say_showing import _say_showing


def test_nothing_is_said_when_nothing_plays(capsys: pytest.CaptureFixture[str]) -> None:
    _say_showing(None)

    assert capsys.readouterr().out == ""


def test_the_viewer_hears_what_will_be_interrupted(capsys: pytest.CaptureFixture[str]) -> None:
    entry = Entry(title="Моана 2", magnet="magnet:?x=1", pos=660.0, dur=5978.0)

    _say_showing(("ключ", entry))

    printed = capsys.readouterr().out
    where = f" {phrase('showing.at', pos='0:11:00')}"
    assert phrase("showing.busy", what="«Моана 2»", where=where) in printed
