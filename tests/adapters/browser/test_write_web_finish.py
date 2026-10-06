"""Проверяет запись одноразовой команды конца серии вкладке."""

from pathlib import Path

from torrcast.adapters.browser.read_web_finish import read_web_finish
from torrcast.adapters.browser.write_web_finish import write_web_finish


def test_the_finish_command_keeps_its_tab_key_and_target_second(tmp_path: Path) -> None:
    write_web_finish(tmp_path, "k1", 119.0)

    assert read_web_finish(tmp_path) == {"key": "k1", "at": 119.0}
