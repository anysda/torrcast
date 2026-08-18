"""Что каталог отдаёт глобом сетки: только наши куски и ничего постороннего."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack._segment_files import _names, _paths

if TYPE_CHECKING:
    from pathlib import Path


def _stock(root: Path) -> None:
    for name in ("v0.ts", "v12.ts", "mix12.ts", "pack.csv", "v3.ts.part"):
        (root / name).write_bytes(b"x")


def test_only_our_segments_are_seen_and_the_neighbours_are_not(tmp_path: Path) -> None:
    """Склейка, список нарезки и недописанный хвост кусками сетки не считаются.

    Ровно на этом стоит признак «кусок дописан»: появление СЛЕДУЮЩЕГО ``v*.ts``.
    Посчитай мы соседей - и недописанный кусок уехал бы наружу как готовый.
    """
    _stock(tmp_path)

    assert sorted(_names(tmp_path)) == ["v0.ts", "v12.ts"]


def test_the_paths_are_the_same_pieces_and_they_are_paths(tmp_path: Path) -> None:
    """Пути и имена говорят об одном и том же наборе: иначе уборка стёрла бы не то."""
    _stock(tmp_path)

    found = _paths(tmp_path)

    assert sorted(path.name for path in found) == ["v0.ts", "v12.ts"]
    assert all(path.parent == tmp_path and path.exists() for path in found)


def test_an_empty_directory_is_an_empty_answer_and_not_a_failure(tmp_path: Path) -> None:
    """Пустой каталог - это ноль кусков, а не поломка: с него начинается каждый прогон."""
    assert _names(tmp_path) == [] and _paths(tmp_path) == []
