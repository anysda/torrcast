"""Проверяет снятие одноразовой команды конца серии вкладке."""

from pathlib import Path

from torrcast.adapters.browser.clear_web_finish import clear_web_finish
from torrcast.adapters.browser.read_web_finish import read_web_finish
from torrcast.adapters.browser.write_web_finish import write_web_finish


def test_clearing_an_absent_finish_command_does_not_raise(tmp_path: Path) -> None:
    clear_web_finish(tmp_path)


def test_a_cleared_finish_command_is_no_longer_offered_to_the_tab(tmp_path: Path) -> None:
    write_web_finish(tmp_path, "k1", 119.0)

    clear_web_finish(tmp_path)

    assert read_web_finish(tmp_path) == {}
