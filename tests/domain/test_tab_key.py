"""Ключ вкладки по её слову о себе: движок, система и хватает ли ей умений."""

from __future__ import annotations

import pytest

from torrcast.domain.tab_key import tab_key

#: ``User-Agent`` настоящих вкладок: три движка щупа (playwright 1.62) и телефоны.
CHROMIUM_LINUX = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "HeadlessChrome/151.0.7922.34 Safari/537.36"
)
FIREFOX_LINUX = "Mozilla/5.0 (X11; Linux x86_64; rv:153.0) Gecko/20100101 Firefox/153.0"
#: WebKit щупа врёт о себе «Macintosh»: он и есть незамеренный WebKit.
WEBKIT_PROBE = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/26.5 Safari/605.1.15"
)
IPHONE_SAFARI = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
)
IPHONE_CHROME = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) CriOS/130.0 Mobile/15E148 Safari/604.1"
)
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Mobile Safari/537.36"
)
ANDROID_FIREFOX = "Mozilla/5.0 (Android 14; Mobile; rv:130.0) Gecko/130.0 Firefox/130.0"
WINDOWS_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
#: Всё, что щедрая вкладка говорит о себе: MSE и h264 High 5.1.
ABLE = "mse.hls.avc51"


@pytest.mark.parametrize(
    ("agent", "key"),
    [
        (CHROMIUM_LINUX, "chromium-linux"),
        (FIREFOX_LINUX, "gecko-linux"),
        (WEBKIT_PROBE, "webkit-mac"),
        (IPHONE_SAFARI, "webkit-ios"),
        (IPHONE_CHROME, "webkit-ios"),
        (ANDROID_CHROME, "chromium-android"),
        (ANDROID_FIREFOX, "gecko-android"),
        (WINDOWS_CHROME, "chromium-windows"),
        ("", "other-other"),
    ],
)
def test_the_key_names_the_engine_and_the_system(agent: str, key: str) -> None:
    """Движок и система по ``User-Agent``: на iPhone и Chrome - это WebKit, Android - не Linux."""
    assert tab_key(agent, ABLE) == key


def test_a_tab_that_said_nothing_has_no_key() -> None:
    """Нет куки - вкладка молчала (или это не вкладка вовсе, а HA и бот)."""
    assert tab_key(CHROMIUM_LINUX, None) == ""


@pytest.mark.parametrize("said", ["", "hls", "mse", "mse.hevc", "avc51"])
def test_a_tab_without_mse_or_high_5_1_is_bare(said: str) -> None:
    """Без MSE или без h264 High 5.1 щедрые пороги не про неё, какой бы ни был движок."""
    assert tab_key(CHROMIUM_LINUX, said) == "chromium-linux-bare"


def test_managed_media_source_counts_as_mse() -> None:
    """ManagedMediaSource (Safari 17+) - тот же путь hls.js, что MSE."""
    assert tab_key(IPHONE_SAFARI, "mms.hls.avc51") == "webkit-ios"
