"""Профиль вкладки: кому он достаётся и что он вкладке больше не режет."""

from __future__ import annotations

from torrcast.adapters.chromecast.profile_detector import ProfileDetector
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.recode.targets import _targets
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.by_key import by_key
from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV, BROWSER, CAUTIOUS
from torrcast.domain.tune import tune


def _refuse(address: str, timeout: float = 0.0) -> Device:
    raise AssertionError("паспорт спрашивать было не у кого")


def _heavy_slots(config: Config) -> tuple[int, ...]:
    """Слоты кодировщика для куска копии 21 Мбит/с на 10 с (26 МБ) и лёгкого за ним."""
    chosen = ProfileDetector(ask=_refuse).detect(config)
    tuned = tune(config, chosen.profile)
    lines = Grid(bounds=(0.0, 10.0), duration=20.0, on_keys=True)
    weights = Weights(raw=(21.0, 4.0))
    return _targets(weights, lines, tuned.recode_at_mbit, chosen.profile.max_segment_bytes)


def test_a_tab_with_nobody_to_hand_over_to_gets_the_browser_profile() -> None:
    """Приёмник - вкладка и ТВ не назван: пороги телевизора вкладке ни к чему."""
    chosen = ProfileDetector(ask=_refuse).detect(Config(receiver="browser"))

    assert chosen.profile is BROWSER
    assert chosen.how


def test_a_tab_named_by_cast_tv_browser_gets_it_too() -> None:
    """``cast --tv browser`` пишет в ``tv`` само слово ``browser``: ТВ это не называет."""
    config = Config(receiver="browser", tv="browser")

    assert ProfileDetector(ask=_refuse).detect(config).profile is BROWSER


def test_a_tab_next_to_a_named_tv_keeps_the_tv_profile() -> None:
    """«На ТВ» отдаёт телевизору тот же поток: при названном ТВ вкладка его не меняет."""
    chosen = ProfileDetector(ask=_refuse).detect(Config(receiver="browser", tv="10.0.0.50"))

    assert chosen.profile is CAUTIOUS


def test_a_named_profile_still_wins_over_the_tab() -> None:
    """Ключ руками - последнее слово и для вкладки."""
    config = Config(receiver="browser", receiver_profile="androidtv")

    assert ProfileDetector(ask=_refuse).detect(config).profile is ANDROID_TV


def test_the_browser_profile_is_registered_by_key() -> None:
    """Профиль лежит в реестре, иначе ключ ``browser`` руками даёт осторожный."""
    assert by_key("browser") is BROWSER


def test_chromium_gets_no_codec_it_cannot_decode() -> None:
    """MSE Chromium на щупе: hvc1/hev1 и mp4v нет - только перекод, h264 8 бит - копия."""
    assert BROWSER.plays_copy("h264", depth=8, frame=1080)
    assert not BROWSER.plays_copy("hevc", depth=8, frame=1080)
    assert not BROWSER.plays_copy("hevc", depth=10, frame=2160)
    assert not BROWSER.plays_copy("mpeg4", depth=8, frame=720)
    assert not BROWSER.plays_copy("h264", depth=10, frame=1080)


def test_a_heavy_copy_is_no_longer_cut_for_the_tab() -> None:
    """Кусок 26 МБ на 21 Мбит/с вкладка играет копией, а телевизору его режут."""
    assert _heavy_slots(Config(receiver="browser")) == ()
    assert _heavy_slots(Config(receiver="browser", tv="10.0.0.50")) == (0,)
