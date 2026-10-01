"""Проверяет путь отметки последней серии."""

from pathlib import Path

from torrcast.adapters.browser.web_last_path import WEB_LAST_FILE, web_last_path


def test_the_path_lives_next_to_the_segments_it_names(tmp_path: Path) -> None:
    assert web_last_path(tmp_path) == tmp_path / WEB_LAST_FILE
