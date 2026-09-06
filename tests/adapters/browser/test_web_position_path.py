"""Проверяет путь записи последней позиции вкладки."""

from pathlib import Path

from torrcast.adapters.browser.web_position_path import WEB_POSITION_FILE, web_position_path


def test_the_path_lives_next_to_the_segments_it_names(tmp_path: Path) -> None:
    assert web_position_path(tmp_path) == tmp_path / WEB_POSITION_FILE
