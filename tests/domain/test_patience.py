"""Зеркало :mod:`torrcast.domain.patience`."""

from __future__ import annotations

from torrcast.domain.patience import Patience


def test_the_session_dies_the_moment_the_patience_runs_out() -> None:
    """Пока терпение идёт - показ жив; кончилось - медиасессии больше нет."""
    patience = Patience(23.5, 2)

    assert not patience.gave_up(23.4)
    assert patience.gave_up(23.5)


def test_the_retries_are_spread_evenly_over_the_patience() -> None:
    """Перезаборы куска разнесены по терпению поровну, а не сыплются подряд."""
    patience = Patience(30.0, 2)

    assert not patience.retry_due(9.9, 0), "первая треть терпения ещё не вышла"
    assert patience.retry_due(10.0, 0)
    assert not patience.retry_due(19.9, 1), "вторая идёт от своей трети, а не от нуля"
    assert patience.retry_due(20.0, 1)
    assert not patience.retry_due(29.9, 2), "перезаборы кончились - дальше только терпеть"


def test_a_receiver_without_retries_only_waits_out_its_patience() -> None:
    """У приёмника, который куски не перезабирает, терпение тратится и без единой попытки."""
    patience = Patience(4.0, 0)

    assert not patience.retry_due(3.9, 0)
    assert patience.gave_up(4.0)
