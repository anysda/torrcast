"""Проверяет: сценарий следующей серии читает паспорт через порт Prober, а не в обход него.

Фейк ставится тем же словом, каким его ставит боевая проводка
(:func:`torrcast.runtime.wire_search.wire_search` зовёт
:func:`torrcast.usecases.episode_duration._configure_episode_duration`), а не строкой поверх
модульной переменной. Мера меряет цель: не то, что фейк умеет отвечать сам себе, а то, что
настоящий сценарий (:func:`torrcast.usecases.episode_duration._duration`) действительно
доходит до назначенного порта и переносит его ответ в запись.
"""

from __future__ import annotations

from tests.fakes.prober import FakeProber
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.ports.prober import Prober
from torrcast.ports.state_store.slot import install as install_state
from torrcast.usecases.episode_duration import _configure_episode_duration, _duration


def test_the_next_episode_scenario_reads_its_passport_through_the_port() -> None:
    """Отрицательная проба: сценарий, читающий паспорт мимо порта, фейка не увидит вовсе."""
    install_state(FakeStateStore())
    fake = FakeProber(Media(duration=4000.0, video="h264", height=1080, width=1920))
    port: Prober = fake
    _configure_episode_duration(port)
    entry = Entry(
        title="Сериал",
        magnet="magnet:?x=1",
        kind="tv",
        file_idx=2,
        episodes=[[1, 1, 1, 10_000_000_000]],
    )

    result = _duration("ключ", entry, "http://127.0.0.1:1/x")

    assert fake.sources == ["http://127.0.0.1:1/x"], "сценарий обязан дойти до назначенного порта"
    assert result.dur == 4000.0


def test_the_deadline_the_scenario_asks_with_reaches_the_port() -> None:
    """Срок ответа - часть вопроса: без него ожидание паспорта следующей серии было бы вечным."""
    install_state(FakeStateStore())
    fake = FakeProber(Media(duration=1.0))
    _configure_episode_duration(fake)
    entry = Entry(title="Кино", magnet="magnet:?x=2")

    _duration("другой ключ", entry, "http://127.0.0.1:1/y")

    assert fake.timeouts == [WORKER_DUR]
