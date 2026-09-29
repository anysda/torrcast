"""Зеркало :func:`_notes` про паспорт дефолтной картины: кому его ждать, кому нет."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import plans, release
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.cast_command._notes import _notes
from torrcast.usecases.select._prep import _Prep


def _prep(video: TorrFile) -> _Prep:
    prep = _Prep(number=1, release=release())
    prep.video = video
    prep.files = [video]
    prep.media = _media()
    return prep


def _media() -> Media:
    return Media(
        duration=7200.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=8e6,
    )


class _Namesake:
    """Паспорт дефолтной картины, у которой справка знает тёзку того же года."""

    def __init__(self) -> None:
        self.asked = 0

    def get(self) -> Origin:
        self.asked += 1
        return Origin(title="Cars 1", year=2006, namesake="Тачки (сериал, 2006)")


def _pick(menu: list[Any], picked: Any, passport: _Namesake) -> None:
    video = TorrFile(index=1, name="кино/film.mkv", size=(3 * 1024**3))
    _notes(
        Config(bitrate_warn_mbit=40.0),
        cast(Any, menu),
        picked,
        _prep(video),
        _media(),
        0,
        release(),
        video,
        cast(Any, passport),
        Args(query=["тачки"]),
    )


def test_a_picture_picked_by_number_does_not_wait_for_the_default_passport(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Паспорт добирается про дефолт меню: выбранной номером он чужой, и ждать его незачем.

    «Играть» карточки сериала №3 стояло на нём 0.94 с перед юнитом, а тёзку
    чужой картины строка приписала бы выбранной.
    """
    menu, passport = plans(3), _Namesake()
    menu[2].picture.year = 2006

    _pick(menu, menu[2], passport)

    assert passport.asked == 0
    assert "Тачки (сериал, 2006)" not in capsys.readouterr().out


def test_the_default_picture_still_hears_about_its_namesake(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Дефолт меню паспорт дожидается: строка про тёзку остаётся на своём месте."""
    menu, passport = plans(3), _Namesake()

    _pick(menu, menu[0], passport)

    assert passport.asked == 1
    assert "Тачки (сериал, 2006)" in capsys.readouterr().out
