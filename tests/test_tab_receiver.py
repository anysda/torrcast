"""Вкладка узнаётся по ящику, а показ на ТВ - по полю ``tv`` того же ящика."""

from pathlib import Path

import pytest

from hass.tab_receiver import tab_receiver
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.config import Config


def test_a_box_of_the_tab_itself_is_a_tab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="t", at=0.0, key="k1")

    assert tab_receiver(Config())


def test_a_box_of_a_show_on_the_tv_is_not_a_tab(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="t", at=0.0, key="k1", tv=True)

    assert not tab_receiver(Config())


def test_no_box_is_not_a_tab(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))

    assert not tab_receiver(Config())
