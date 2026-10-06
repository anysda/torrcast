"""Приёмник одного запуска: вкладке - если просила она, иначе телевизор машины."""

from __future__ import annotations

import pytest

from torrcast.domain.config import Config
from torrcast.domain.show_receiver import show_receiver


def test_without_here_a_browser_machine_with_a_tv_plays_on_the_tv() -> None:
    config = Config(receiver="browser", tv="living-room")
    assert show_receiver(config, False).receiver == "chromecast"
    assert show_receiver(config, False).tv == "living-room"
    assert config.receiver == "browser"  # настройка машины не пишется


def test_here_always_plays_in_the_tab() -> None:
    for receiver in ("chromecast", "browser"):
        config = Config(receiver=receiver, tv="living-room")
        assert show_receiver(config, True).receiver == "browser"


@pytest.mark.parametrize(
    ("receiver", "tv"),
    [("browser", None), ("browser", ""), ("browser", "browser"), ("chromecast", "living-room")],
)
def test_otherwise_the_machine_setting_stays(receiver: str, tv: str | None) -> None:
    """Отрицательная проба: без названного ТВ вкладке некуда отдавать показ."""
    config = Config(receiver=receiver, tv=tv)  # type: ignore[arg-type]
    assert show_receiver(config, False) is config
