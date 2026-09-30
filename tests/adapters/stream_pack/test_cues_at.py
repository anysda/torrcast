"""Где индекс mkv: прогрев продолжения с середины греет его вслед за заголовком."""

from __future__ import annotations

import inspect
from pathlib import Path

from tests.fakes.disk_range_reader import DiskRangeReader
from torrcast.adapters.frames.http_range_reader import HttpRangeReader
from torrcast.adapters.frames.keyframes import HEAD_PEEK
from torrcast.adapters.stream_pack.cues_at import STEP, cues_at

#: Номер элемента ``Cues`` в EBML.
CUES_ID = b"\x1c\x53\xbb\x6b"


def test_the_head_of_an_mkv_names_the_place_of_its_cues(clip: str) -> None:
    at = cues_at(clip, source=DiskRangeReader)

    assert at is not None
    assert Path(clip).read_bytes()[at : at + 4] == CUES_ID


def test_a_head_without_a_seek_head_names_nothing(tmp_path: Path) -> None:
    film = tmp_path / "фильм.mkv"
    film.write_bytes(b"\x00" * 4096)

    assert cues_at(str(film), source=DiskRangeReader) is None


def test_the_product_reads_the_head_through_the_swarm() -> None:
    assert inspect.signature(cues_at).parameters["source"].default is HttpRangeReader


def test_a_show_that_starts_stops_the_read_of_the_head(clip: str) -> None:
    """Прочие звенья прогрева уступают показу на каждом мегабайте, голова читалась до 120 с."""
    readers: list[DiskRangeReader] = []
    answers = iter([True, False])

    def source(url: str) -> DiskRangeReader:
        readers.append(DiskRangeReader(url))
        return readers[-1]

    assert cues_at(clip, lambda: next(answers, False), source=source) is None
    assert readers[0].requests == 1


def test_without_a_show_the_head_is_read_to_its_end_in_steps(clip: str) -> None:
    readers: list[DiskRangeReader] = []

    def source(url: str) -> DiskRangeReader:
        readers.append(DiskRangeReader(url))
        return readers[-1]

    assert cues_at(clip, lambda: True, source=source) == cues_at(clip, source=DiskRangeReader)
    assert readers[0].requests == -(-min(HEAD_PEEK, Path(clip).stat().st_size) // STEP)
