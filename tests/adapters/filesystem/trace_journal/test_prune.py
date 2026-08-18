"""Ротация ленты: неделя по сроку, потолок по весу, и всё это раз в сутки на каталог."""

from __future__ import annotations

import time
from pathlib import Path

from torrcast.adapters.filesystem.trace_journal.prune import MAX_BYTES, RETAIN_DAYS, _prune


def _day(back: int) -> str:
    return time.strftime("%Y%m%d", time.localtime(time.time() - back * 86400))


def _tape(directory: Path, back: int, size: int) -> Path:
    path = directory / f"trace-{_day(back)}.jsonl"
    path.write_text("x" * size, encoding="utf-8")
    return path


def test_a_week_is_kept_and_everything_older_goes(tmp_path: Path) -> None:
    """Срок хранения - неделя: старше сносится, ровесник границы остаётся.

    Неделя - это то, за что вообще имеет смысл спрашивать след: «что было в прошлый раз»
    человек спрашивает днями, а не месяцами, а платит за ответ местом на диске.
    """
    assert RETAIN_DAYS == 7
    old = _tape(tmp_path, RETAIN_DAYS + 3, 10)
    young = _tape(tmp_path, 1, 10)

    _prune("", tmp_path)

    assert not old.exists()
    assert young.exists()


def test_over_the_ceiling_the_oldest_days_go_first(tmp_path: Path) -> None:
    """Потолок места считается с новых суток к старым: свежее важнее.

    Считай ротация с другого конца - и переполненный каталог сносил бы ровно ту ленту,
    ради которой её и держат: сегодняшнюю.
    """
    tapes = [_tape(tmp_path, back, 80) for back in (3, 2, 1)]

    _prune("", tmp_path, ceiling=100)

    assert [path.exists() for path in tapes] == [False, False, True]


def test_the_rotation_runs_once_a_day_per_directory(tmp_path: Path) -> None:
    """Второй прогон в те же сутки по тому же каталогу не делает ничего.

    На каждый пакет записей ротация означала бы лишние ``stat`` в фоне показа; ключ несёт
    и каталог, чтобы смена пути ленты прокручивала ротацию по новому месту сразу.
    """
    marked = _prune("", tmp_path)
    old = _tape(tmp_path, RETAIN_DAYS + 3, 10)

    assert _prune(marked, tmp_path) == marked
    assert old.exists(), "те же сутки и тот же каталог - второй обход не нужен"

    other = tmp_path / "другой"
    other.mkdir()
    assert _prune(marked, other) != marked, "другой каталог - своя ротация, а не тот же ключ"


def test_the_ceiling_is_a_real_number_of_bytes_not_a_placeholder() -> None:
    """Потолок назван в байтах: 64 МиБ недельного следа - это про диск, а не про вкус."""
    assert MAX_BYTES == 64 * 1024 * 1024
