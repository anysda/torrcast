"""Сверка куска с полки: войдёт ли декодер в голову, нарезанную прогревом."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from torrcast.adapters.stream_pack.piece_opens import piece_opens

_SPS, _PPS, _AUD = b"\x00\x00\x00\x01\x67\x64", b"\x00\x00\x01\x68\xee", b"\x00\x00\x01\x09\xf0"
_IDR, _I, _P = b"\x00\x00\x01\x65\x88", b"\x00\x00\x01\x41\x9a", b"\x00\x00\x01\x41\x9b"
_MMCO = b"[h264 @ 0x5] mmco: unref short failure\n"


def _answer(stdout: bytes, stderr: bytes = b"") -> Any:
    """Подставной ``run``: копия куска отдаёт ``stdout``, декодер - ``stderr``; помнит входы."""
    fed: list[bytes] = []

    def _run(command: list[str], **kwargs: Any) -> Any:
        fed.append(kwargs.get("input", b""))
        return SimpleNamespace(returncode=0, stdout=stdout, stderr=stderr)

    _run.fed = fed  # type: ignore[attr-defined]
    return _run


def test_pictures_before_the_first_sps_are_not_the_entry() -> None:
    """Кусок прогрева начинается посреди GOP: вход - первый SPS, а не первый срез куска."""
    run = _answer(_AUD + _P + _AUD + _SPS + _PPS + _IDR, stderr=_MMCO)

    assert piece_opens(Path("v1.ts"), run=run) is True
    assert len(run.fed) == 1


def test_the_decoder_hears_the_entry_pictures_and_no_dangling_delimiter() -> None:
    """Вход без IDR решает декодер: от SPS ровно 16 картинок, без AUD следующей.

    Число держится числом, а не именем константы: 8 и 32 тоже прошли бы сверку по имени.
    """
    picture = _AUD + _P
    stream = _P + _SPS + _PPS + _I + picture * 40
    quiet, loud = _answer(stream), _answer(stream, stderr=_MMCO)

    assert piece_opens(Path("v1.ts"), run=quiet) is True
    assert piece_opens(Path("v1.ts"), run=loud) is False
    assert quiet.fed[1] == _SPS[1:] + _PPS + _I + picture * 15


def test_a_piece_without_parameter_sets_is_not_a_verdict() -> None:
    """Нет SPS или ffmpeg не ответил - ``None``, и показ берёт голову прежним путём."""
    assert piece_opens(Path("v1.ts"), run=_answer(_I + _P, stderr=_MMCO)) is None

    def _hang(*a: Any, **k: Any) -> Any:
        raise subprocess.TimeoutExpired("ffmpeg", 1.0)

    assert piece_opens(Path("v1.ts"), run=_hang) is None


def test_the_whole_check_stays_within_five_seconds_of_the_click() -> None:
    """Копия куска и декодер делят один потолок 5 с: декодеру остаток, а не весь потолок.

    Сверка стоит на клике до первого кадра; потолок пробного прогона (60 с) или полный
    потолок декодеру после медленной копии держали бы показ дольше слагаемого бюджета старта.
    """
    asked: list[float] = []
    now = iter((0.0, 3.5))

    def _run(command: list[str], *, timeout: float, **k: Any) -> Any:
        asked.append(timeout)
        if "pipe:0" in command:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return SimpleNamespace(returncode=0, stdout=_SPS + _PPS + _I + _P, stderr=b"")

    assert piece_opens(Path("v1.ts"), run=_run, clock=lambda: next(now)) is None
    assert asked == [5.0, 1.5]
    assert 3.5 + asked[1] <= 5.0


def _piece(where: Path, params: str) -> Path:
    """Кусок TS, как его режет прогрев: копия с 2.5 с, впереди картинки без опорного."""
    film, piece = where / "film.ts", where / "v1.ts"
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "testsrc2=size=320x240:rate=24", "-t", "6", "-c:v", "libx264",
            "-x264-params",
            f"keyint=48:min-keyint=48:open-gop=1:bframes=3:scenecut=0:{params}", str(film),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(film), "-ss", "2.5",
         "-c", "copy", str(piece)],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return piece


@pytest.mark.ffmpeg
def test_an_open_gop_piece_without_mmco_on_entry_keeps_the_shelf(tmp_path: Path) -> None:
    """Настоящим ffmpeg: I без IDR, но кадры за ним не смотрят назад - голова с полки годна."""
    assert piece_opens(_piece(tmp_path, "ref=1:b-pyramid=none")) is True


@pytest.mark.ffmpeg
def test_a_piece_whose_pictures_point_before_its_entry_is_refused(tmp_path: Path) -> None:
    """Настоящим ffmpeg: MMCO на картинки до входа, как у v534 «Интерстеллара», - ``False``."""
    assert piece_opens(_piece(tmp_path, "ref=4:b-pyramid=normal")) is False
