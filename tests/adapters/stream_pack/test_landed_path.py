"""Проверяет путь файла настоящего места старта."""

from pathlib import Path

from torrcast.adapters.stream_pack.landed_path import LANDED_FILE, landed_path


def test_the_path_lives_next_to_the_output_it_names(tmp_path: Path) -> None:
    """Файл лежит в том же каталоге, что и упаковка - его видят оба процесса показа."""
    assert landed_path(tmp_path) == tmp_path / LANDED_FILE
