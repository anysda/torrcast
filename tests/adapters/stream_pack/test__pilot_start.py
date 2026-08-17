"""Проверяет пробный прогон: ответ переводится в ленту фильма, а уезд вперёд остаётся."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.conftest import module_of
from torrcast.adapters.stream_pack._pilot_start import _film_start, _pilot_start

module = module_of("torrcast.adapters.stream_pack._pilot_start")

#: На столько уезжает вперёд лента контейнера в фикстуре ниже.
SHIFT = 600.0


@pytest.fixture(autouse=True)
def _own_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Начало ленты помнится на весь процесс; каждой проверке нужна своя память."""
    monkeypatch.setattr(module, "_FILM_START", {})


@pytest.fixture
def clip_shifted(clip: str, tmp_path: Path) -> str:
    """Тот же ролик в mpegts, чьи метки начинаются не с нуля - так лежат .ts и .m2ts."""
    path = tmp_path / "shifted.ts"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", clip,
         "-c", "copy", "-output_ts_offset", f"{SHIFT:g}",
         "-muxdelay", "0", "-muxpreload", "0", "-f", "mpegts", "-y", str(path)],
        check=True, capture_output=True,
    )  # fmt: skip
    return str(path)


def test_a_file_that_did_not_open_leaves_the_boundary_as_it_was() -> None:
    """Не вышло - считаем, что встали ровно на границе: врать про место нечем."""
    assert _pilot_start("http://нет-такого.invalid/поток", 12.5, timeout=5.0) == 12.5
    assert _film_start("http://нет-такого.invalid/поток", timeout=5.0) == 0.0


@pytest.mark.ffmpeg
def test_a_container_that_starts_from_zero_needs_no_translation(clip: str) -> None:
    """У mkv и mp4 видео начинается с нуля: сдвиг нулевой и ответ не меняется ни на миллисекунду."""
    assert _film_start(clip) == 0.0
    assert _pilot_start(clip, 41.0) == pytest.approx(40.0, abs=0.5), "докатка mkv потеряна"


@pytest.mark.ffmpeg
def test_the_shift_of_the_whole_container_is_subtracted(clip_shifted: str) -> None:
    """🔴 TC-629. ``-ss`` считается от начала контейнера, а ``-copyts`` печатает метку с ним.

    Замер на стенде: контейнер, чьё видео начинается с 600.006, на ``-ss 40.000`` отвечает
    640.006 - и это число ехало в резы как «где встал прогон», уводя весь список в минус.
    """
    assert _film_start(clip_shifted) == pytest.approx(SHIFT, abs=1.0)
    assert _pilot_start(clip_shifted, 41.0) == pytest.approx(42.0, abs=0.5)


@pytest.mark.ffmpeg
def test_the_start_of_the_film_is_measured_once_per_file(clip: str) -> None:
    """ffprobe тут стоит десятые доли секунды локально и секунды на живой раздаче,
    а заходов на фильм много: число считается раз и помнится.
    """
    _film_start(clip)
    assert module._FILM_START[clip] == 0.0
    module._FILM_START[clip] = 3.5  # второй раз ffprobe не зовут
    assert _film_start(clip) == 3.5
