"""Снос каталога: сносится всё содержимое, а отсутствие каталога - не беда."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.filesystem.remove_tree import remove_tree


def test_a_directory_goes_away_with_everything_inside(tmp_path: Path) -> None:
    nest = tmp_path / "run" / "deep"
    nest.mkdir(parents=True)
    (nest / "v0.ts").write_bytes(b"x")

    remove_tree(tmp_path / "run")

    assert not (tmp_path / "run").exists()


def test_a_missing_directory_is_not_a_failure(tmp_path: Path) -> None:
    """Убирает этим уже погашенный показ: падать ему тут не на чем."""
    remove_tree(tmp_path / "нет такого")
