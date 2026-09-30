"""Сверка входа копией: IDR ли первый кадр с ``-ss``."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from torrcast.adapters.stream_pack.opens_clean import opens_clean
from torrcast.domain.hls_wait import ENTRY_TIMEOUT, PILOT_TIMEOUT

if TYPE_CHECKING:
    from pathlib import Path

_SPS, _SEI = b"\x00\x00\x00\x01\x67\x64", b"\x00\x00\x01\x06\x05"


_IDR_SLICE, _I_SLICE = b"\x00\x00\x01\x65\x88", b"\x00\x00\x01\x41\x9a"
_MMCO = b"[h264 @ 0x5] mmco: unref short failure\n"


def _answer(stdout: bytes, code: int = 0, stderr: bytes = b"") -> Any:
    """Подставной ``run``: копия отдаёт ``stdout``, декодер - ``stderr``; помнит, что звали."""
    asked: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> Any:
        asked.append(command)
        return SimpleNamespace(returncode=code, stdout=stdout, stderr=stderr)

    _run.asked = asked  # type: ignore[attr-defined]
    return _run


def test_an_idr_entry_is_clean_without_decoding() -> None:
    """Параметры и SEI впереди не в счёт: первый срез IDR - вход чистый, декодер не нужен."""
    run = _answer(_SPS + _SEI + _IDR_SLICE, stderr=_MMCO)

    assert opens_clean("f", 1.0, run=run) is True
    assert len(run.asked) == 1


def test_a_non_idr_entry_is_judged_by_the_decoder_on_the_same_bytes() -> None:
    """I без IDR решает декодер: жалоба - ``False``, тишина - ``True``; раздачу не читают дважды."""
    stream = _SPS + _SEI + _I_SLICE
    quiet, loud = _answer(stream), _answer(stream, stderr=_MMCO)

    assert opens_clean("f", 1.0, run=quiet) is True
    assert opens_clean("f", 1.0, run=loud) is False
    assert "pipe:0" in loud.asked[1] and "f" not in loud.asked[1]


def test_silence_is_not_a_verdict() -> None:
    """Ни среза, ни ответа ffmpeg - ``None``, и показ идёт прежним путём."""
    assert opens_clean("f", 1.0, run=_answer(_SPS)) is None
    assert opens_clean("f", 1.0, run=_answer(b"", code=1)) is None

    def _hang(*a: Any, **k: Any) -> Any:
        raise subprocess.TimeoutExpired("ffmpeg", 1.0)

    assert opens_clean("f", 1.0, run=_hang) is None


def test_both_steps_share_one_short_ceiling() -> None:
    """Копия и декодер делят один потолок сверки, а не ждут каждый свой.

    Потолок - отдельное слагаемое бюджета старта
    (:data:`torrcast.usecases.start_budget.START_BUDGET`); с потолком пробного прогона
    (60 с) холодный рой держал бы показ на сверке минуту сверх суммы фаз.
    """
    asked: list[float] = []
    now = iter((0.0, 3.5))

    def _run(command: list[str], *, timeout: float, **k: Any) -> Any:
        asked.append(timeout)
        if "pipe:0" in command:
            raise subprocess.TimeoutExpired("ffmpeg", timeout)
        return SimpleNamespace(returncode=0, stdout=_I_SLICE, stderr=b"")

    assert opens_clean("f", 1.0, run=_run, clock=lambda: next(now)) is None
    assert asked == [ENTRY_TIMEOUT, ENTRY_TIMEOUT - 3.5]
    assert ENTRY_TIMEOUT <= 5.0 < PILOT_TIMEOUT


def _film(path: Path, params: str) -> str:
    """Шесть секунд x264 с открытым GOP: IDR только в начале, дальше I без IDR."""
    subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi",
            "-i", "testsrc2=size=320x240:rate=24", "-t", "6", "-c:v", "libx264",
            "-preset", "medium", "-x264-params",
            f"keyint=48:min-keyint=48:open-gop=1:bframes=3:scenecut=0:{params}", str(path),
        ],
        check=True,
        capture_output=True,
    )  # fmt: skip
    return str(path)


@pytest.mark.ffmpeg
def test_an_open_gop_entry_the_tab_plays_is_not_sent_to_recode(tmp_path: Path) -> None:
    """Настоящим ffmpeg: x264 open-gop без MMCO на входе - копией, хоть вход и не IDR.

    Вкладка (Chromium, hls.js 1.5.17) играла этот же вход (2.5 с) 3 из 3: кадр через
    0.14-0.25 с, 359-363 кадра за 15 с. Сплошной перекод тут - лишний процессор на весь показ.
    """
    film = _film(tmp_path / "open.mkv", "repeat-headers=1:ref=1:b-pyramid=none")

    assert opens_clean(film, 0.0) is True
    assert opens_clean(film, 2.5) is True


@pytest.mark.ffmpeg
def test_an_entry_whose_pictures_point_before_it_is_sent_to_recode(tmp_path: Path) -> None:
    """Настоящим ffmpeg: MMCO на картинки до входа - как у BD-AVC 5212 МБ - в перекод.

    Такой x264 (ref=4, b-pyramid) вкладка не открыла 3 из 3 - ``PIPELINE_ERROR_DECODE``,
    ровно как BD-AVC «Интерстеллара» с 177.837; декодер ffmpeg - «mmco: unref short failure».
    """
    film = _film(tmp_path / "mmco.mkv", "repeat-headers=1:ref=4:b-pyramid=normal")

    assert opens_clean(film, 0.0) is True
    assert opens_clean(film, 2.5) is False


@pytest.mark.ffmpeg
def test_an_entry_without_its_parameter_sets_is_sent_to_recode(tmp_path: Path) -> None:
    """Настоящим ffmpeg: SPS/PPS только в шапке mkv - копия с I без IDR их не несёт.

    ``h264_mp4toannexb`` вставляет заголовки лишь перед IDR; вкладка на таком входе не
    заводит даже буфер видео (``bufferAppendError``) - 2 из 2.
    """
    film = _film(tmp_path / "bare.mkv", "ref=1")

    assert opens_clean(film, 2.5) is False
