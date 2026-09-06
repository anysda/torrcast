"""Проверяет путь почтового ящика вкладки."""

from pathlib import Path

from torrcast.adapters.browser.web_box_path import WEB_BOX_FILE, web_box_path


def test_the_path_lives_next_to_the_segments_it_names(tmp_path: Path) -> None:
    """Ящик лежит в том же каталоге, что и сегменты - его видят оба процесса показа."""
    assert web_box_path(tmp_path) == tmp_path / WEB_BOX_FILE
