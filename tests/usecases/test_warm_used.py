"""Зеркало мерки прогретого: число приходит от среды, каталог знает она же."""

from __future__ import annotations

import pytest

from tests.fakes.composition import use_health_environment
from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.usecases.warm_used import warm_used


def test_the_weight_of_the_warmed_comes_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сколько сказала среда, столько прогретым и занято: диска мерка сама не трогает."""
    use_health_environment(monkeypatch, FakeHealthEnvironment(warmed=15 * 1024**3))

    assert warm_used() == 15 * 1024**3


def test_an_empty_disk_is_a_plain_zero_and_not_a_missing_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Прогретого нет - ноль, а не пусто: на этом числе стоит арифметика резерва."""
    use_health_environment(monkeypatch, FakeHealthEnvironment())

    assert warm_used() == 0


def test_a_new_environment_is_answered_by_the_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Среду сменили - мерка отвечает уже по ней: значение не кэшируется на импорте."""
    use_health_environment(monkeypatch, FakeHealthEnvironment(warmed=1))
    first = warm_used()
    use_health_environment(monkeypatch, FakeHealthEnvironment(warmed=2))

    assert (first, warm_used()) == (1, 2)
