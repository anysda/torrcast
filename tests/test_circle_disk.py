"""Круги на диске: переживают перезапуск, живут сутки, файл ограничен и не рвётся."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import web.circle_disk as circle_disk
from torrcast.domain.raw_result import RawResult
from web.circle_disk import DAY, CircleDisk

_ROW = RawResult("Тачки / Cars (2006) 1080p", "a" * 40, 5, 66, "rutracker", 2, ("a", "b"), ("x",))
_TOLD = [("search", "тачки", 0.0, ("Knaben",), [_ROW]), ("spare", "", 4.5, (), [])]


def _disk(tmp_path: Path, now: list[float]) -> CircleDisk:
    return CircleDisk(path=lambda: tmp_path / "circles.json", clock=lambda: now[0])


def test_a_kept_circle_is_read_back_by_a_restarted_process_for_a_day(tmp_path: Path) -> None:
    now = [1000.0]
    _disk(tmp_path, now).keep("тачки", _TOLD)

    restarted = _disk(tmp_path, now)
    assert restarted.told("тачки") == _TOLD
    now[0] += DAY
    assert restarted.told("тачки") is None
    assert list(tmp_path.iterdir()) == [tmp_path / "circles.json"]


def test_the_file_keeps_only_the_newest_circles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(circle_disk, "ENTRIES", 2)
    now = [0.0]
    disk = _disk(tmp_path, now)
    for query in ("вверх", "тачки", "вверх", "матрица"):
        now[0] += 1
        disk.keep(query, _TOLD)

    assert sorted(json.loads((tmp_path / "circles.json").read_text())) == ["вверх", "матрица"]


def test_a_broken_file_is_a_miss_not_a_failure(tmp_path: Path) -> None:
    (tmp_path / "circles.json").write_text('{"тачки": {"at": 1e12, "told": [["search"]]}}')

    assert _disk(tmp_path, [0.0]).told("тачки") is None
