"""Сборка сеанса показа: звенья из их настоящих домов, а юнит - с порта."""

from pathlib import Path
from typing import Any

from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.domain.config import Config
from torrcast.runtime.playback_session import playback_session


def test_the_session_asks_the_unit_that_the_root_installed(show_unit: FakeShowUnit) -> None:
    """Живость и ключ показа сеанс спрашивает у назначенного юнита, а не у systemd."""
    show_unit.alive = True
    show_unit.playing = "movie:моана-2"

    session = playback_session()

    assert isinstance(session, UnitPlaybackSession)
    assert session.active() is True
    assert session.key() == "movie:моана-2"


def test_a_named_configuration_wins_over_reading_the_file() -> None:
    config: Any = type("Config", (), {"receiver": "mock"})()

    assert playback_session(lambda: config).receiver_name() == "mock"


def test_the_browser_show_stream_address_comes_from_its_box(tmp_path: Path) -> None:
    """У показа вкладки нет маршрута до ТВ - её адрес лежит в ящике, куда его положил показ.

    Файл настроек про ``receiver: browser`` одного запуска не знает, поэтому без ящика
    кадр играющей картины на машине без телевизора было бы не с чего снять.
    """
    config = Config(tv="", hls_dir=str(tmp_path))
    write_web_box(tmp_path, url="http://127.0.0.1:8083/index.m3u8", title="t", at=0.0, key="k")
    assert playback_session(lambda: config).stream_address() == "http://127.0.0.1:8083/index.m3u8"


def test_without_a_route_and_without_a_box_the_address_stays_unknown(tmp_path: Path) -> None:
    """Ни маршрута, ни ящика - честное «адрес неизвестен», а не выдуманная ссылка."""
    config = Config(tv="", hls_dir=str(tmp_path))
    assert playback_session(lambda: config).stream_address() == "stream address is not known"
