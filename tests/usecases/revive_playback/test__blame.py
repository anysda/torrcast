"""Зеркало обвинения: прежде чем винить приёмник, показ спрашивает ИСТОЧНИК."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import FakeSupply, feed_with_segments
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._blame import _may, _why
from torrcast.usecases.revive_playback._revival_state import _RevivalState
from torrcast.usecases.warm.warmer import Warmer


def test_a_silent_source_takes_the_blame_and_reaches_the_packing(tmp_path: Path) -> None:
    """Источник молчит - виноват он, и упаковка узнаёт причину от нас же."""
    supply = FakeSupply(silence="TorrServer не отвечает")
    state = _RevivalState(clock=FakeClock(), supply=cast(StreamSource, supply))
    feed = feed_with_segments(tmp_path)

    why = _why(state, feed)

    assert why == "TorrServer не отвечает"
    assert state.blamed is True and state.dropped is False
    assert str(feed.offline) == "TorrServer не отвечает"


def test_a_healthy_source_leaves_the_receiver_to_blame(tmp_path: Path) -> None:
    """Источник спрошен и здоров, упаковка молчит - показ бросил сам приёмник."""
    supply = FakeSupply()
    state = _RevivalState(clock=FakeClock(), supply=cast(StreamSource, supply))

    why = _why(state, feed_with_segments(tmp_path))

    assert why == "приёмник бросил показ"
    assert state.dropped is True and state.blamed is False
    assert supply.asked > 0, "приговор приёмнику ставится только после вопроса источнику"


def test_a_fully_warmed_film_never_blames_the_supply(tmp_path: Path) -> None:
    """Фильм целиком на диске - снабжение ему не нужно, и диагноз рою печататься не должен.

    Замер 24-08-2026: упаковку на паузе погасили мы сами, фильм лежал на диске целиком,
    а показ написал «рой привозит 0.00 Мбит/с при нужных 9.22» - враньё дважды.
    """

    class _Done:
        done = True
        warmed = 0.0

    supply = FakeSupply(silence="рой привозит 0.00 Мбит/с - снабжения не хватает")
    state = _RevivalState(clock=FakeClock(), supply=cast(StreamSource, supply))

    why = _why(state, feed_with_segments(tmp_path), cast(Warmer, _Done()))

    assert why == "приёмник бросил показ"
    assert supply.asked == 0, "спрашивать источник не о чем: прогретый фильм сети не ждёт"


def test_a_finished_warm_up_needs_no_network_at_all(tmp_path: Path) -> None:
    """Фильм лёг на диск целиком - возврата сети ждать нечего, поднимаем сразу."""

    class _Done:
        done = True
        warmed = 0.0

    state = _RevivalState(clock=FakeClock())

    assert _may(state, feed_with_segments(tmp_path), cast(object, _Done()), 0.0) is True  # type: ignore[arg-type]


def test_a_source_that_is_still_down_keeps_the_receiver_untouched(tmp_path: Path) -> None:
    """Пока источник лежит, LOAD в приёмник не летит вовсе: жечь его терпение незачем."""
    supply = FakeSupply(silence="TorrServer не отвечает")
    state = _RevivalState(clock=FakeClock(), supply=cast(StreamSource, supply), blamed=True)

    assert _may(state, feed_with_segments(tmp_path), None, 0.0) is False


def test_a_returned_source_still_waits_for_the_stream_to_be_ready(tmp_path: Path) -> None:
    """Служба ответила - обрыв снят, но LOAD ждёт выложенного куска у сохранённой позиции."""
    supply = FakeSupply()
    state = _RevivalState(clock=FakeClock(), supply=cast(StreamSource, supply), blamed=True)
    feed = feed_with_segments(tmp_path)
    feed.offline = "сети нет"

    ready = _may(state, feed, None, 0.0)

    assert str(feed.offline) == ""
    assert state.why == "источник вернулся - жду готовности потока"
    assert ready is (feed.front(0.0) > 0.0)
