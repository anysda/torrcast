"""Сверка входа копией: IDR ли первый кадр с ``-ss``."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from torrcast.adapters.stream_pack.opens_clean import opens_clean

if TYPE_CHECKING:
    from pathlib import Path

_SPS, _SEI = b"\x00\x00\x00\x01\x67\x64", b"\x00\x00\x01\x06\x05"


def _answer(stdout: bytes, code: int = 0) -> Any:
    return lambda *a, **k: SimpleNamespace(returncode=code, stdout=stdout)


def test_the_first_slice_decides() -> None:
    """Параметры и SEI впереди не в счёт: смотрится первый срез картинки."""
    assert opens_clean("f", 1.0, run=_answer(_SPS + _SEI + b"\x00\x00\x01\x65\x88")) is True
    assert opens_clean("f", 1.0, run=_answer(_SPS + _SEI + b"\x00\x00\x01\x41\x9a")) is False


def test_silence_is_not_a_verdict() -> None:
    """Ни среза, ни ответа ffmpeg - ``None``, и показ идёт прежним путём."""
    assert opens_clean("f", 1.0, run=_answer(_SPS)) is None
    assert opens_clean("f", 1.0, run=_answer(b"", code=1)) is None

    def _hang(*a: Any, **k: Any) -> Any:
        raise subprocess.TimeoutExpired("ffmpeg", 1.0)

    assert opens_clean("f", 1.0, run=_hang) is None


@pytest.mark.ffmpeg
def test_an_open_gop_key_frame_is_not_an_entry(tmp_path: Path) -> None:
    """Настоящим ffmpeg: open-GOP x264 ставит IDR только в начало, дальше - I без IDR.

    Так устроены и BD-AVC релизы: контейнер зовёт опорным каждый I-кадр, а декодер,
    начавший с середины, получает ссылки на картинки, которых не видел.
    """
    film = tmp_path / "open.mkv"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "testsrc2=size=160x120:rate=25", "-t", "5", "-c:v", "libx264",
            "-x264-params", "keyint=50:min-keyint=50:open-gop=1:bframes=2:scenecut=0",
            str(film),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    assert opens_clean(str(film), 0.0) is True
    assert opens_clean(str(film), 2.5) is False
