"""Кому ключ вкладки приносит замеренные пороги, а кому - ровно выбор ``dev``."""

from __future__ import annotations

import pytest

from tests.domain.test_tab_key import (
    ABLE,
    ANDROID_CHROME,
    CHROMIUM_LINUX,
    FIREFOX_LINUX,
    IPHONE_CHROME,
    IPHONE_SAFARI,
    WEBKIT_PROBE,
    WINDOWS_CHROME,
)
from torrcast.adapters.chromecast.profile_detector import ProfileDetector
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.for_tab import MEASURED, for_tab
from torrcast.domain.profile import ANDROID_TV, BROWSER, CAUTIOUS
from torrcast.domain.tab_key import tab_key


def _refuse(address: str, timeout: float = 0.0) -> Device:
    raise AssertionError("паспорт спрашивать было не у кого")


def _dev(config: Config) -> Choice:
    """Выбор ``dev``: тот же детектор, без слова вкладки."""
    return ProfileDetector(ask=_refuse).detect(config)


def test_only_the_probes_chromium_and_firefox_are_measured() -> None:
    """Список замеренных - ровно то, что гонял tabprobe: WebKit щупа не прошёл 58 МБ."""
    assert {tab_key(CHROMIUM_LINUX, ABLE), tab_key(FIREFOX_LINUX, ABLE)} == MEASURED


@pytest.mark.parametrize("tv", ["", "browser"])
@pytest.mark.parametrize("agent", [CHROMIUM_LINUX, FIREFOX_LINUX])
def test_a_measured_tab_alone_gets_the_browser_profile(agent: str, tv: str) -> None:
    """Замеренная вкладка, передать показ некому: её пороги."""
    config = Config(receiver="browser", tv=tv)
    tab = tab_key(agent, ABLE)

    chosen = for_tab(_dev(config), config, tab)

    assert chosen.profile is BROWSER
    assert tab in chosen.how


@pytest.mark.parametrize(
    "tab",
    [
        tab_key(agent, said)
        for agent in (WEBKIT_PROBE, IPHONE_SAFARI, IPHONE_CHROME, ANDROID_CHROME, WINDOWS_CHROME)
        for said in (ABLE, "mms.hls.avc51", "")
    ]
    + ["chromium-linux-bare", "gecko-linux-bare", "other-other", "chromium-linux-x"],
)
def test_an_unmeasured_tab_gets_exactly_what_dev_gave(tab: str) -> None:
    """Отрицательная проба: незамеренная вкладка не хуже ``dev``, профиль тот же самый."""
    config = Config(receiver="browser")

    chosen = for_tab(_dev(config), config, tab)

    assert chosen.profile is _dev(config).profile is CAUTIOUS
    assert tab in chosen.how, "журнал не называет вкладку, которой отказано"


def test_a_tab_that_said_nothing_changes_nothing() -> None:
    """``cast play --here`` из консоли и HA ключа не несут: выбор ``dev`` как есть."""
    config = Config(receiver="browser")
    dev = _dev(config)

    assert for_tab(dev, config, "") is dev


@pytest.mark.parametrize(
    "config",
    [
        Config(receiver="chromecast", tv="10.0.0.50"),
        Config(receiver="browser", tv="10.0.0.50"),
        Config(receiver="browser", receiver_profile="androidtv"),
    ],
    ids=["tv", "tab-next-to-a-tv", "named"],
)
def test_a_measured_tab_does_not_move_a_tv_or_a_named_profile(config: Config) -> None:
    """Машина с ТВ играет во вкладке поток ТВ, а ключ руками - последнее слово."""
    before = Choice(ANDROID_TV, "паспорт")

    assert for_tab(before, config, "chromium-linux") is before
