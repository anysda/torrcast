"""Проверяет узкий путь стрелки к вкладке: штатный конец без общего пульта."""

from pathlib import Path

import pytest

from hass.tab_finish import tab_finish
from torrcast.adapters.browser.read_web_finish import read_web_finish
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.config import Config
from web.tv_session import SESSION


def test_a_live_tab_gets_a_finish_command_for_its_own_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="t", at=12.0, key="k1")

    assert tab_finish(Config(), 119.0)
    assert read_web_finish(tmp_path) == {"key": "k1", "at": 119.0}


def test_a_cast_tab_does_not_get_a_finish_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="t", at=12.0, key="k1")
    monkeypatch.setattr(SESSION, "owns", lambda key: key == "k1")

    assert not tab_finish(Config(), 119.0)
    assert read_web_finish(tmp_path) == {}
