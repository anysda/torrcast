"""Проверяет путь одноразовой команды конца серии вкладке."""

from pathlib import Path

from torrcast.adapters.browser.web_finish_path import WEB_FINISH_FILE, web_finish_path


def test_the_finish_command_lives_next_to_the_tab_mailbox(tmp_path: Path) -> None:
    assert web_finish_path(tmp_path) == tmp_path / WEB_FINISH_FILE
