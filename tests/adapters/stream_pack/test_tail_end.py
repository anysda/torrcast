"""Конец последнего куска фильма: список нарезки по картинке плюс звук за ней."""

from __future__ import annotations

import dataclasses
import subprocess
from typing import TYPE_CHECKING

import pytest

import torrcast.adapters.stream_pack.tail_end as tail_module
from tests.usecases.feed_pack.world import FakeProc, packer
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.packer_finished import _finished
from torrcast.adapters.stream_pack.tail_end import tail_end
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path


def test_an_fmp4_tail_is_measured_through_the_header_of_its_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Без головы прогона кусок ``.m4s`` не читается, и мера молча давала ``nan``.

    Стенд, «Теория большого взрыва» s2e5 на Android TV: хвост перепаковывался по кругу,
    приёмник стоял за 5.7 с до конца, потом ошибка и «досмотрено».
    """
    asked: list[tuple[str, str | None]] = []

    def measure(piece: Path, header: Path | None) -> float:
        asked.append((piece.name, header.name if header else None))
        return 0.9

    monkeypatch.setattr(tail_module, "piece_overhang", measure)
    grid = Grid.uniform(30.0, 10.0)
    state = packer(tmp_path, grid=grid, container=FMP4)

    assert tail_end(state, grid, 29.0) == pytest.approx(29.9)
    assert asked == [("v2.m4s", "init.mp4")]


def test_the_listed_end_loses_the_origin_and_an_unread_piece_keeps_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Метки списка сдвинуты на начало ленты; не прочли кусок - остаётся конец из списка."""
    grid = dataclasses.replace(Grid.uniform(30.0, 10.0), origin=0.5)
    state = packer(tmp_path, grid=grid)
    monkeypatch.setattr(tail_module, "piece_overhang", lambda _piece, _head: float("nan"))
    assert tail_end(state, grid, 29.5) == pytest.approx(29.0)
    monkeypatch.setattr(tail_module, "piece_overhang", lambda _piece, _head: 1.0)
    assert tail_end(state, grid, 29.5) == pytest.approx(30.0)


@pytest.mark.ffmpeg
def test_a_real_fmp4_run_whose_sound_outlasts_the_picture_reads_to_the_end(
    tmp_path: Path,
) -> None:
    """Настоящий прогон упаковки в fMP4: картинка 20 с, звук 22 с - это конец, не обрыв.

    Отрицательная проба: вернуть прежнюю меру по голому куску (без головы) - прогон
    назван недочитанным, и хвост ушёл бы на перепаковку по кругу.
    """
    source = tmp_path / "tail.mkv"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=25:duration=20",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=22", "-c:v", "libx264", "-g", "25",
         "-preset", "ultrafast", "-c:a", "aac", str(source)],
        check=True, capture_output=True,
    )  # fmt: skip
    probe = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0"]
    duration = float(subprocess.run([*probe, str(source)], check=True, capture_output=True).stdout)
    grid = Grid.uniform(duration, 10.0)
    state = packer(tmp_path, grid=grid, container=FMP4, proc=FakeProc(code=0))
    command = ffmpeg_pack_command(
        str(source), 0, str(state.run), grid, 0, 0.0, readrate=0.0, container=FMP4
    )
    subprocess.run(command, check=True, capture_output=True)

    assert (state.run / f"v{grid.count - 1}.m4s").exists(), "хвостового куска нет - мерить нечего"
    assert _finished(state) is True, "здоровый хвост fMP4 со звуком за картинкой назван обрывом"
