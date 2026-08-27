"""Щуп стыка звука меряет тики дорожки, а не метки показа, и длину кадра читает из потока."""

from __future__ import annotations

import importlib.util
import struct
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "seamticks", Path(__file__).resolve().parent.parent / "scripts/seamticks.py"
)
assert SPEC is not None and SPEC.loader is not None
ticks = importlib.util.module_from_spec(SPEC)
sys.modules["seamticks"] = ticks
SPEC.loader.exec_module(ticks)


def _printing(text: str, code: int = 0, err: str = "") -> Any:
    """Подделка ffprobe, печатающая ровно то, что печатает настоящий."""

    def _probe(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], code, text, err)

    return _probe


def _span(first: int, end: int, frames: int, scale: int = 48000, rate: int = 48000) -> Any:
    return ticks.Span("v", first, end, frames, scale, rate)


def test_a_seam_of_zero_ticks_is_continuous_sound() -> None:
    """Конец предыдущего и начало следующего сошлись тик в тик - дыры нет."""
    assert ticks.seam(_span(0, 475136, 464), _span(475136, 957440, 471)) == 0


def test_a_hole_and_a_mark_backwards_are_told_apart_by_the_sign() -> None:
    """Плюс - дыра, минус - метки назад: приёмник платит за оба, но лечатся они по-разному."""
    assert ticks.seam(_span(0, 475136, 464), _span(476160, 957440, 471)) == 1024
    assert ticks.seam(_span(0, 475136, 464), _span(0, 482304, 471)) == -475136


def test_the_frame_length_follows_the_rate_read_from_the_stream() -> None:
    """⚠️ Прибор с зашитой длиной кадра читает сплошной звук 44.1 кГц как дыры."""
    assert _span(0, 0, 0, scale=48000, rate=48000).per_frame == 1024
    # Та же дорожка в шкале 90 кГц: кадр AAC - ровно 1920 тиков, а не 1024.
    assert _span(0, 0, 0, scale=90000, rate=48000).per_frame == 1920
    assert _span(0, 0, 0, scale=44100, rate=44100).per_frame == 1024


def test_the_end_of_a_chunk_is_taken_from_its_last_sample() -> None:
    """Конец - последний сэмпл плюс его длина: муксер бывает неровен, а стык там, где байты."""
    got = ticks.span("v1", [(475136, 1024), (476160, 1024), (477184, 1024)], 48000, 48000)

    assert (got.first, got.end, got.frames) == (475136, 478208, 3)


def test_a_chunk_without_a_single_sample_is_not_measured_silently() -> None:
    with pytest.raises(ticks.ProbeError):
        ticks.span("v1", [], 48000, 48000)


def test_a_bare_chunk_is_fed_together_with_its_head(tmp_path: Path) -> None:
    """🔴 Голый ``moof mdat`` не открывается ничем: ``trun track id unknown``."""
    chunk, head = tmp_path / "v1.m4s", tmp_path / "init.mp4"
    chunk.write_bytes(struct.pack(">I", 8) + b"moof")
    head.write_bytes(b"head")

    assert ticks.feed(chunk, head) == f"concat:{head}|{chunk}"


def test_a_chunk_that_carries_its_own_head_is_fed_as_it_is(tmp_path: Path) -> None:
    """Склейка приезжает со своим заголовком - приставлять второй значит мерить не то."""
    chunk, head = tmp_path / "mix1.m4s", tmp_path / "init.mp4"
    chunk.write_bytes(struct.pack(">I", 12) + b"ftypiso6" + struct.pack(">I", 8) + b"moof")
    head.write_bytes(b"head")

    assert ticks.feed(chunk, head) == str(chunk)


def test_the_scale_and_the_rate_are_both_taken_from_the_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ticks.subprocess, "run", _printing("1/48000,48000\n"))

    assert ticks.track("x") == (48000, 48000)


def test_a_stream_without_sound_is_refused_rather_than_measured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ticks.subprocess, "run", _printing(""))

    with pytest.raises(ticks.ProbeError):
        ticks.track("x")


def test_ffprobe_refusing_to_read_a_chunk_is_not_read_as_a_zero_seam(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отказ прибора - это отказ, а не сплошной звук: молчание тут врало бы в пользу поломки."""
    monkeypatch.setattr(
        ticks.subprocess, "run", _printing("", 1, "trun track id unknown, no tfhd was found")
    )

    with pytest.raises(ticks.ProbeError):
        ticks.packets("x")


def test_samples_without_marks_are_dropped_and_not_counted_as_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ffprobe печатает N/A там, где метки нет; посчитать её нулём значит выдумать стык."""
    monkeypatch.setattr(ticks.subprocess, "run", _printing("475136,1024\nN/A,1024\n476160,1024\n"))

    assert ticks.packets("x") == [(475136, 1024), (476160, 1024)]


def test_the_report_says_outright_whether_every_seam_is_zero() -> None:
    """Мера карточки - «стык звука нулевой в тиках», и щуп обязан отвечать на неё словом."""
    even = [_span(0, 475136, 464), _span(475136, 957440, 471), _span(957440, 1435648, 467)]

    report = ticks.report(even)

    assert report["стык звука нулевой"] is True
    assert (report["нулевых"], report["стыков"]) == (2, 2)
    assert report["самый широкий, тиков"] == 0
    assert report["кадр, тиков"] == 1024


def test_the_widest_seam_is_reported_with_its_sign_and_in_frames() -> None:
    torn = [_span(0, 475136, 464), _span(0, 482304, 471), _span(957440, 1435648, 467)]

    report = ticks.report(torn)

    assert report["стык звука нулевой"] is False
    assert report["самый широкий, тиков"] == -475136
    assert report["самый широкий, кадров"] == -464.0
