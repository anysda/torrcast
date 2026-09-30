"""Профиль вкладки: кому он достаётся и что он вкладке больше не режет."""

from __future__ import annotations

from pathlib import Path

from torrcast.adapters.chromecast.profile_detector import ProfileDetector
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.recode.targets import _targets
from torrcast.adapters.recode.weights import Weights
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.by_key import by_key
from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV, BROWSER, CAUTIOUS
from torrcast.domain.tune import tune
from torrcast.usecases.playback._recoder import _recoder


def _refuse(address: str, timeout: float = 0.0) -> Device:
    raise AssertionError("паспорт спрашивать было не у кого")


def _heavy_slots(config: Config, mbit: float = 21.0, span: float = 10.0) -> tuple[int, ...]:
    """Слоты кодировщика для куска копии ``mbit`` на ``span`` секунд и лёгкого за ним."""
    chosen = ProfileDetector(ask=_refuse).detect(config)
    tuned = tune(config, chosen.profile)
    lines = Grid(bounds=(0.0, span), duration=2 * span, on_keys=True)
    weights = Weights(raw=(mbit, 4.0))
    return _targets(weights, lines, tuned.recode_at_mbit, chosen.profile.segment_limit)


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


def test_a_blu_ray_peak_plays_as_a_copy_in_the_tab() -> None:
    """Пик BD-рипа 30.8 Мбит/с на 5 с (19 МБ) вкладке - копия, Android TV его пережимает."""
    assert _heavy_slots(Config(receiver="browser"), mbit=30.8, span=5.0) == ()
    androidtv = Config(receiver="browser", receiver_profile="androidtv")
    assert _heavy_slots(androidtv, mbit=30.8, span=5.0) == (0,)


def test_a_piece_the_tab_plays_is_not_cut_for_the_byte_cap() -> None:
    """30.8 Мбит/с на 10 с - это 38 МБ: вкладке копия (предел 80), Android TV - перекод (28)."""
    assert _heavy_slots(Config(receiver="browser"), mbit=30.8, span=10.0) == ()
    androidtv = Config(receiver="browser", receiver_profile="androidtv")
    assert _heavy_slots(androidtv, mbit=30.8, span=10.0) == (0,)


def test_a_piece_over_the_tabs_limit_is_still_recoded() -> None:
    """Предел вкладки остаётся: 30.8 Мбит/с на 25 с - это 96 МБ, 115 МБ Chromium не держит."""
    assert _heavy_slots(Config(receiver="browser"), mbit=30.8, span=25.0) == (0,)


def test_tv_profiles_refuse_what_their_grid_aims_at() -> None:
    """У телевизоров цель сетки и предел - одно число, как было до профиля вкладки."""
    for profile in (CAUTIOUS, ANDROID_TV):
        assert profile.segment_limit == profile.max_segment_bytes
    assert BROWSER.segment_limit > BROWSER.max_segment_bytes


def test_the_show_recoder_takes_the_tabs_limit(tmp_path: Path) -> None:
    """Кодировщик показа судит кусок пределом профиля: 30 МБ вкладке копия, приставке - нет."""

    def slots(config: Config) -> tuple[int, ...]:
        chosen = ProfileDetector(ask=_refuse).detect(config)
        grid = Grid.uniform(300.0)
        tuned = tune(config, chosen.profile)
        profile = chosen.profile
        made = _recoder("http://ts", 0, grid, tmp_path, tuned, video_mbit=24.0, profile=profile)
        assert made is not None
        return made.targets

    assert slots(Config(receiver="browser", recode=True)) == ()
    assert len(slots(Config(receiver="browser", receiver_profile="androidtv", recode=True))) == 30
