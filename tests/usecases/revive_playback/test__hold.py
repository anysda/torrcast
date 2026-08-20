"""Зеркало держателя показа: круг опроса, конец сеанса и передача погасшего показа лестнице."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import (
    FakeReceiver,
    FakeSupply,
    PlainReceiver,
    feed_with_segments,
)
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.start_settings import FIRST_FRAME_POLL
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.watch import Watch


@pytest.fixture(autouse=True)
def _silent_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Флажок картинки в зеркале никуда не пишется: меряем решение, а не файл."""
    composition.use_playing_mark(monkeypatch, lambda _path: None)


def test_a_show_that_cannot_be_raised_ends_by_itself(tmp_path: Path) -> None:
    """Приёмник погас, поднимать нечем - держатель возвращает ответ лестницы, а не висит."""
    receiver = PlainReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    ended = _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        clock=FakeClock(now=1000.0),
    )

    assert ended is False, "лестница не поднимала - это обычный конец показа"


def test_a_long_pause_ends_the_show(tmp_path: Path) -> None:
    """Пауза длиной с вечер - показ окончен: юнит гасим, а не держим до утра."""
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(100.0, "PLAYING")] + [(100.0, "PAUSED")] * 4000)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps, "круг опроса обязан спать между вопросами приёмнику"


def test_the_receiver_is_asked_more_often_until_the_first_frame(tmp_path: Path) -> None:
    """До первого кадра приёмник спрашивается чаще: флажок «картинка» ставится на опросе.

    При шаге 2 с строка «старт NN с» запаздывала за настоящим кадром на 1.9-3.8 с.
    Первый же показанный кадр возвращает обычный шаг - учащение живёт ровно в окне
    старта, а не весь показ.
    """
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver(
        [(100.0, "PLAYING")] * 3 + [(101.0, "PLAYING")] + [(101.0, "PAUSED")] * 2000
    )

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps[:3] == [FIRST_FRAME_POLL] * 3, "указатель стоит - опрос учащён"
    assert set(clock.sleeps[3:]) == {2.0}, "кадр показан - окно старта кончилось"


def test_a_pause_before_the_first_frame_keeps_the_usual_poll(tmp_path: Path) -> None:
    """PLAYING без кадра, а следом пауза на пульте - окно старта закрыто: указатель не двигается.

    Пауза может длиться час, и учащённый опрос там жёг бы запросы к приёмнику впустую:
    кадру взяться неоткуда.
    """
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(50.0, "PLAYING")] + [(50.0, "PAUSED")] * 2000)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps[0] == FIRST_FRAME_POLL, "PLAYING без кадра - окно старта открыто"
    assert set(clock.sleeps[1:]) == {2.0}, "на паузе опрос не учащается"


def test_a_dead_session_before_the_first_frame_keeps_the_usual_poll(tmp_path: Path) -> None:
    """Приёмник сказал PLAYING и умер, не показав кадра: темнота - не окно старта.

    В темноте показ ждёт возврата источника и лестницу подъёма, а указателю в мёртвой
    сессии взяться неоткуда - учащённый опрос там жёг бы приёмник впустую всю темноту.
    """
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(100.0, "PLAYING")] + [(0.0, "IDLE")] * 50)

    _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert clock.sleeps[0] == FIRST_FRAME_POLL, "PLAYING без кадра - окно старта открыто"
    assert clock.sleeps[1] == 2.0, "сессия мертва - окно старта закрыто"


def test_a_stuck_pointer_at_the_tail_finishes_the_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Указатель стоит у самого конца дольше минуты - сеанс доигран, и переход не теряется."""
    clock = FakeClock(now=1000.0)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", dur=7200.0, pos=7190.0)
    watch = Watch(key="кино", entry=entry)
    receiver = FakeReceiver([(7190.0, "PLAYING")] * 200)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), watch, clock=clock)

    assert ended is True
    assert "считаю доигранным" in capsys.readouterr().out


def test_a_dead_packing_with_a_healthy_source_falls_honestly(tmp_path: Path) -> None:
    """Упаковка сдалась, источник цел - показ падает честной ошибкой, а не молчанием."""
    feed = feed_with_segments(tmp_path)
    feed.fatal = "ffmpeg лёг"

    with pytest.raises(InfraError, match="упаковка оборвалась"):
        _hold(
            cast(Receiver, FakeReceiver()),
            feed,
            supply=cast(StreamSource, FakeSupply()),
            clock=FakeClock(now=1000.0),
        )
