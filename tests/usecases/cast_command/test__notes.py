"""Зеркало строк перед стартом: вес, звук, подмена картины и тёзки - каждый своей строкой."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import plan, release
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.media import Media
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.cast_command._notes import _notes
from torrcast.usecases.select._prep import _Prep


class _Silent:
    """Паспорт картины, которому нечего сказать: строки про год и тёзок молчат."""

    def get(self) -> Origin:
        return Origin()


def _media(mbit: float = 8.0) -> Media:
    return Media(
        duration=7200.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=mbit * 1e6,
    )


def _prep(video: TorrFile) -> _Prep:
    prep = _Prep(number=1, release=release())
    prep.video = video
    prep.files = [video]
    prep.media = _media()
    return prep


def _say(config: Config, media: Media, args: Args) -> str:
    one = plan()
    video = TorrFile(index=1, name="кино/film.mkv", size=(30 * 1024**3))
    _notes(
        config,
        cast(Any, [one]),
        cast(Any, one),
        _prep(video),
        media,
        0,
        release(),
        video,
        cast(Any, _Silent()),
        args,
    )
    return ""


def test_a_heavy_release_warns_about_the_receiver(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Выше порога настроек показ говорит вслух, чем это кончится для приёмника."""
    _say(Config(bitrate_warn_mbit=4.0, recode=False), _media(), Args(query=["кино"]))

    assert "ресивер на таком битрейте может встать" in capsys.readouterr().out


def test_the_same_weight_with_recoding_promises_a_recode_instead(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """С включённым перекодированием та же тяжесть обещает перекод, а не вставший экран."""
    _say(Config(bitrate_warn_mbit=4.0, recode=True), _media(), Args(query=["кино"]))

    assert "тяжёлые куски перекодирую на ходу" in capsys.readouterr().out


def test_a_light_release_says_nothing_about_the_weight(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Под порогом сказать нечего: лишняя строка перед стартом - это шум."""
    _say(Config(bitrate_warn_mbit=40.0), _media(), Args(query=["кино"]))

    assert "Мбит/с" not in capsys.readouterr().out


def test_the_debug_handle_shows_the_insides(capsys: pytest.CaptureFixture[str]) -> None:
    """``--release N`` - отладочный путь: тут внутренности показывать и надо."""
    _say(Config(bitrate_warn_mbit=40.0), _media(), Args(query=["кино"], release=1))

    assert "файл: film.mkv" in capsys.readouterr().out
