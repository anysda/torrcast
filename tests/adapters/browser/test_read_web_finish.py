"""Проверяет чтение одноразовой команды вкладке."""

from pathlib import Path

from torrcast.adapters.browser.read_web_finish import read_web_finish


def test_an_absent_finish_command_reads_as_an_empty_mapping(tmp_path: Path) -> None:
    assert read_web_finish(tmp_path) == {}
