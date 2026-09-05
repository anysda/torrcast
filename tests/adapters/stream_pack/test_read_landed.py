"""Проверяет чтение настоящего места старта: файл важнее закладки, а без файла - закладка."""

from pathlib import Path

from torrcast.adapters.stream_pack.mark_landed import mark_landed
from torrcast.adapters.stream_pack.read_landed import read_landed


def test_the_real_landing_place_wins_over_the_bookmark(tmp_path: Path) -> None:
    """Файл на диске - настоящее место посадки, и закладка ему не указ."""
    mark_landed(tmp_path, 2450.0)
    assert read_landed(tmp_path, default=2500.0) == 2450.0


def test_no_file_means_the_bookmark_is_still_the_best_guess(tmp_path: Path) -> None:
    """Файла нет - значит расходиться с закладкой нечему: отдаём то, что дали доводом."""
    assert read_landed(tmp_path, default=2500.0) == 2500.0


def test_a_broken_record_does_not_win_over_the_bookmark(tmp_path: Path) -> None:
    """Битая запись - не число, и доверия ей не больше, чем отсутствующему файлу."""
    (tmp_path / "landed.at").write_text("не число", encoding="utf-8")
    assert read_landed(tmp_path, default=2500.0) == 2500.0
