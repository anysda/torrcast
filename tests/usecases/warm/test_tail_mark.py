"""Зеркало конца прогретого хвоста: фрагмент CMAF меряется своей длиной, а не молчит.

Фрагменты режет настоящий ffmpeg тем же сегментным муксером HLS, что и прогрев: разбор
боксов сверяется с муксером, а не с пересказом его формата.
"""

from __future__ import annotations

import math
import subprocess
from typing import TYPE_CHECKING

import pytest

from tests.usecases.feed_pack.world import feed, grid, vault
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.segment_container import FMP4
from torrcast.usecases.feed_pack.feed_segment import _warm
from torrcast.usecases.warm.tail_mark import tail_mark

if TYPE_CHECKING:
    from pathlib import Path

#: Сколько фильма обещает сетка: последний кусок с 4-й секунды до 6.5.
FILM = 6.5
STEP = 4.0


def _cut(where: Path, seconds: float) -> None:
    """Фрагменты CMAF по 4 с из ``seconds`` секунд картинки и звука, с заголовком init.mp4."""
    where.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "testsrc=size=320x180:rate=25",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-t", str(seconds), "-c:v", "libx264", "-g", "25", "-c:a", "aac",
        "-f", "hls", "-hls_time", str(STEP), "-hls_segment_type", "fmp4",
        "-hls_playlist_type", "vod", "-hls_fmp4_init_filename", "init.mp4",
        "-hls_segment_filename", str(where / "v%d.m4s"), str(where / "index.m3u8"),
    ]  # fmt: skip
    subprocess.run(command, check=True, timeout=60)


@pytest.mark.ffmpeg
def test_the_end_of_a_fragment_is_its_start_plus_its_longest_track(tmp_path: Path) -> None:
    """Звук хвоста идёт до 6.579, картинка до 6.6 по ffprobe: длина фрагмента - по звуку."""
    _cut(tmp_path, FILM)

    ended = tail_mark(tmp_path / "v1.m4s", tmp_path / "init.mp4", STEP)

    assert ended == pytest.approx(FILM, abs=0.1)


@pytest.mark.ffmpeg
def test_a_torn_fragmented_tail_is_rejected_before_the_show(tmp_path: Path) -> None:
    """Хвост, обрезанный на 5-й секунде из обещанных 6.5, приставке не уходит.

    Отрицательная проба: мера хвоста только по пакетам TS (прежний ``segment_end``) -
    на ``.m4s`` она молчит, и обрезок уходит как здоровый.
    """
    said: list[str] = []
    store = vault(tmp_path, container=FMP4)
    _cut(store.dir, 5.0)
    show = feed(tmp_path, vault=store, grid=grid(FILM, STEP), log=said.append)
    measured = tail_mark(store.path(1), store.head(), STEP)

    assert _warm(show, 1) is None, "обрезанный хвост CMAF уехал зрителю"
    assert not store.path(1).exists()
    assert measured == pytest.approx(5.0, abs=0.1)
    assert said == [phrase("feed.warm_torn", slot=1, missing=f"{FILM - measured:.2f}")]


@pytest.mark.ffmpeg
def test_a_whole_fragmented_tail_reaches_the_show(tmp_path: Path) -> None:
    store = vault(tmp_path, container=FMP4)
    _cut(store.dir, FILM)
    show = feed(tmp_path, vault=store, grid=grid(FILM, STEP))

    assert _warm(show, 1) == store.path(1), "здоровый хвост CMAF забракован"


def test_a_fragment_without_its_header_is_not_judged(tmp_path: Path) -> None:
    """Без заголовка шкал дорожек нет: «не прочли», а не «обрезан»."""
    piece = tmp_path / "v1.m4s"
    piece.write_bytes(b"\x00\x00\x00\x08moof")

    assert math.isnan(tail_mark(piece, tmp_path / "init.mp4", STEP))


def test_an_unreadable_piece_is_not_judged(tmp_path: Path) -> None:
    assert math.isnan(tail_mark(tmp_path / "нет.m4s", tmp_path / "init.mp4", STEP))
