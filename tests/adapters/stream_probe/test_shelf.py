"""Полка кэша: живёт по времени обращения, подрезается редко и сразу до трёх четвертей."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from torrcast.adapters.stream_probe.shelf import _mtime, _touch, _trim

if TYPE_CHECKING:
    from pathlib import Path


def _shelf(root: Path, count: int) -> list[Path]:
    made = []
    for number in range(count):
        item = root / f"{number}.json"
        item.write_text("{}", encoding="utf-8")
        os.utime(item, (number, number))  # чем меньше номер, тем дольше не спрашивали
        made.append(item)
    return made


def test_the_shelf_lives_by_the_time_it_was_asked_for_not_made(tmp_path: Path) -> None:
    """Карта фильма, который смотрят каждый вечер, снимается один раз.

    Вытеснять её за возраст значило бы выбрасывать ровно то, что нужнее всего.
    """
    _shelf(tmp_path, 8)
    oldest = tmp_path / "0.json"

    _touch(oldest)
    _trim(tmp_path, kept=4)

    assert oldest.exists(), "только что спрошенное вытеснять нельзя"
    assert not (tmp_path / "1.json").exists(), "а давно не спрошенное ушло"


def test_a_shelf_under_the_cap_is_not_even_stat_ed(tmp_path: Path) -> None:
    """Обычный старт не платит полным обходом с ``stat``: имена берутся одним ``scandir``."""
    kept = _shelf(tmp_path, 4)

    _trim(tmp_path, kept=8)

    assert all(item.exists() for item in kept)


def test_a_full_shelf_is_cut_down_to_three_quarters_at_once(tmp_path: Path) -> None:
    """Иначе полный обход приходился бы на каждый старт; так - раз на четверть потолка."""
    _shelf(tmp_path, 9)

    _trim(tmp_path, kept=8)

    left = list(tmp_path.glob("*.json"))
    assert len(left) == 6, "9 - (9 - 8 * 3 // 4) = 6"


def test_only_our_own_records_are_touched(tmp_path: Path) -> None:
    """Черновики и замки соседних писателей - не наше дело."""
    _shelf(tmp_path, 9)
    draft = tmp_path / "sundry.tmp"
    draft.write_text("x", encoding="utf-8")

    _trim(tmp_path, kept=1)

    assert draft.exists()


def test_a_missing_shelf_is_not_a_trouble(tmp_path: Path) -> None:
    """Осечка полки - не беда: это кэш, а не источник правды."""
    _trim(tmp_path / "нет", kept=4)
    _touch(tmp_path / "нет.json")


def test_an_unreadable_entry_is_counted_as_the_oldest(tmp_path: Path) -> None:
    """Время спросить не вышло - запись идёт первой на выброс, а не роняет подрезку."""

    class _Gone:
        name = "нет.json"
        path = "/нет/нет.json"

        def stat(self) -> os.stat_result:
            raise OSError("нет такого файла")

    assert _mtime(_Gone()) == 0.0  # type: ignore[arg-type]
