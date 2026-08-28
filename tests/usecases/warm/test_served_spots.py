"""Зеркало сеансовой памяти о точечных перекодах прогретого каталога."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.warm.served_spots import ServedSpots

if TYPE_CHECKING:
    from pathlib import Path


def test_disk_is_read_once_and_then_the_warmer_updates_the_show(tmp_path: Path) -> None:
    """Горячий путь не читает метки, но видит законченный во время показа перекод."""
    directory = tmp_path / "warm"
    directory.mkdir()
    (directory / "v3.rec").touch()
    served = ServedSpots(directory)

    (directory / "v4.rec").touch()
    assert served == {3}, "чужая запись на диск просочилась без сеансового сообщения"

    served.mark(5)
    assert served == {3, 5}, "законченный прогрев не сообщил раздаче про новый перекод"
    assert (directory / "v5.rec").exists(), "сообщение появилось раньше самой метки"
