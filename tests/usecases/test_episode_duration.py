"""Зеркально проверяет чтение паспорта следующей серии."""

from torrcast.domain.entry import Entry
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.usecases.episode_duration import _duration


def test_a_full_passport_is_not_asked_for_twice() -> None:
    entry = Entry(title="Кино", magnet="magnet:?x=1", dur=100.0, depth=8, frame=1080)

    assert _duration("ключ", entry, "http://127.0.0.1:1/x") is entry


def test_the_probe_budget_stays_where_it_was() -> None:
    assert WORKER_DUR == 90.0
