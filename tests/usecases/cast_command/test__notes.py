"""Зеркало строк перед стартом: вес, звук, сборник, подмена картины и тёзки."""

from __future__ import annotations

from typing import Any, cast

import pytest

from tests.usecases.cast_command.world import plan, release
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.config import Config
from torrcast.domain.episode import Episode
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


def _prep(video: TorrFile, files: list[TorrFile] | None = None) -> _Prep:
    prep = _Prep(number=1, release=release())
    prep.video = video
    prep.files = [video] if files is None else files
    prep.media = _media()
    return prep


def _say(
    config: Config,
    media: Media,
    args: Args,
    *,
    files: list[TorrFile] | None = None,
    picked: Any = None,
) -> str:
    one = picked or plan()
    video = TorrFile(index=1, name="кино/film.mkv", size=(30 * 1024**3))
    _notes(
        config,
        cast(Any, [one]),
        cast(Any, one),
        _prep(video, files),
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


def _pack() -> list[TorrFile]:
    """Раздача-сборник: дюжина одинаковых частей и ничего больше."""
    return [TorrFile(index=n, name=f"сборник/часть-{n:02d}.mkv", size=100) for n in range(1, 13)]


def test_the_pack_choice_is_said_aloud(capsys: pytest.CaptureFixture[str]) -> None:
    """Видеофайлов несколько, а взял крупнейший отбор - зритель читает об этом строкой.

    Строка обязана лежать в ВЫВОДЕ клиента, а не только в журнале: зритель сидит перед
    консолью, а журнал юнита он не читает.
    """
    _say(Config(bitrate_warn_mbit=40.0), _media(), Args(query=["кино"]), files=_pack())

    assert "видеофайлов в раздаче 12 - играю крупнейший, его доля 0.08" in capsys.readouterr().out


def test_the_pack_line_is_silent_on_a_lone_video(capsys: pytest.CaptureFixture[str]) -> None:
    """Видеофайл один - выбирать не из чего, и здоровая раздача строкой не засоряется."""
    _say(Config(bitrate_warn_mbit=40.0), _media(), Args(query=["кино"]))

    assert "видеофайлов в раздаче" not in capsys.readouterr().out


def test_the_pack_line_does_not_speak_for_the_viewer(capsys: pytest.CaptureFixture[str]) -> None:
    """``--file N`` - выбор человека, а не авто-решение: «играю крупнейший» было бы ложью."""
    _say(Config(bitrate_warn_mbit=40.0), _media(), Args(query=["кино"], file=3), files=_pack())

    assert "видеофайлов в раздаче" not in capsys.readouterr().out


def test_the_pack_line_does_not_speak_for_the_series(capsys: pytest.CaptureFixture[str]) -> None:
    """Сериалу файл называет серия, а не размер: строка про крупнейший была бы ложью."""
    one = plan()
    one.series = _Series(want=Episode(1, 1))
    _say(
        Config(bitrate_warn_mbit=40.0),
        _media(),
        Args(query=["кино"]),
        files=_pack(),
        picked=one,
    )

    assert "видеофайлов в раздаче" not in capsys.readouterr().out
