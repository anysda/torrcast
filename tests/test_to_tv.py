"""Проверяет каст идущего показа на ТВ: ``POST /api/to-tv``."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from tests.fakes.receiver import FakeReceiver
from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.adapters.browser.write_web_position import write_web_position
from torrcast.domain.config import Config
from torrcast.domain.position import Position
from torrcast.ports.receiver import Receiver
from web.request import Request
from web.to_tv import _echo, to_tv
from web.tv_session import SESSION, TvSession


def _post() -> Request:
    return Request("POST", "/api/to-tv", {}, {})


def _wired(monkeypatch: pytest.MonkeyPatch, tv: str = "192.168.1.104") -> FakeReceiver:
    monkeypatch.setattr("web.to_tv.load_config", lambda: Config(tv=tv))
    receiver = FakeReceiver(Position(0.0, 0.0))
    monkeypatch.setattr(SESSION, "factory", lambda address, profile: receiver)
    monkeypatch.setattr(SESSION, "poll_seconds", 0.01)
    monkeypatch.setattr(SESSION, "_receiver", None)
    return receiver


@pytest.fixture(autouse=True)
def _stop_any_cast_left_running() -> Iterator[None]:
    """Убирает опрос, если тест поднял каст и не снял его: без этого фоновый поток
    держателя (:mod:`web.tv_session`) жил бы до конца всего прогона тестов."""
    yield
    SESSION.stop()


def test_no_configured_tv_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch, tv="")

    answer = to_tv(_post())

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "no_tv"}


def test_nothing_playing_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)

    answer = to_tv(_post())

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "nothing_playing"}


def test_the_running_show_is_cast_without_restarting_the_pack(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    receiver = _wired(monkeypatch)
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")
    write_web_position(tmp_path, key="k1", pos=88.0, dur=8000.0, phase="playing", wall=0.0)

    answer = to_tv(_post())

    assert answer.code == 202
    assert receiver.plays == [("http://x/out.m3u8", "Interstellar", 88.0)]


def test_a_stale_mailbox_position_is_ignored_for_a_fresh_box(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    receiver = _wired(monkeypatch)
    write_web_position(
        tmp_path, key="old-session", pos=999.0, dur=8000.0, phase="playing", wall=0.0
    )
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=5.0, key="k1")

    answer = to_tv(_post())

    assert answer.code == 202
    assert receiver.plays == [("http://x/out.m3u8", "Interstellar", 5.0)]


def test_the_tv_position_becomes_the_one_the_product_remembers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ТЗ §7.5.3: пока каст идёт, секунду в файл места кладёт опрос приёмника ТВ.

    Так закладка двигается по тому, что человек ДОСМОТРЕЛ на телевизоре, а не по плёнке
    вкладки, которая всё это время идёт беззвучно и сама по себе. Слушатель тут зовётся
    руками, а не ожиданием опроса: сам опрос сторожит :func:`tests.test_tv_session.
    test_the_live_cast_is_polled_periodically_so_the_position_stays_fresh`, и второй
    тест на стенных часах стоил бы прогону секунд, ничего не добавив.
    """
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)
    caught: list[Callable[[Position], None] | None] = []
    armed = TvSession._arm

    def arming(
        session: TvSession, receiver: Receiver, echo: Callable[[Position], None] | None = None
    ) -> None:
        caught.append(echo)
        armed(session, receiver, echo)

    monkeypatch.setattr(TvSession, "_arm", arming)
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")

    assert to_tv(_post()).code == 202
    assert caught and caught[0] is not None, "держателю не дали слушателя места"
    caught[0](Position(742.0, 8000.0, playing=True))

    record = read_web_position(tmp_path)
    assert record is not None
    assert record["key"] == "k1", "место ТВ уехало под чужим ключом и не читается"
    assert record["pos"] == 742.0
    assert record["phase"] == "playing"


def test_the_listener_goes_quiet_once_the_mailbox_moves_to_another_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Слушатель места умолкает вместе со сменой ящика, а не переживает её."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    _wired(monkeypatch)
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Interstellar", at=12.0, key="k1")

    assert to_tv(_post()).code == 202
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Dune", at=0.0, key="k2")
    heard = _echo(tmp_path, "k1")
    heard(Position(742.0, 8000.0, playing=True))

    assert read_web_position(tmp_path) is None, "место ТВ легло поверх нового показа"
