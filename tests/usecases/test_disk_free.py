"""Зеркало мерки места: путь уезжает среде, а число приходит от неё."""

from __future__ import annotations

import pytest

from tests.fakes.composition import use_health_environment
from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.usecases.disk_free import disk_free


def test_the_free_space_comes_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сколько сказала среда, столько и свободно: диска мерка сама не трогает."""
    use_health_environment(monkeypatch, FakeHealthEnvironment(free=7 * 1024**3))

    assert disk_free("/var/lib/torrcast") == 7 * 1024**3


def test_a_new_environment_is_answered_by_the_new_one(monkeypatch: pytest.MonkeyPatch) -> None:
    """Среду сменили - мерка отвечает уже по ней: значение не кэшируется на импорте."""
    use_health_environment(monkeypatch, FakeHealthEnvironment(free=1))
    first = disk_free("/tmp")
    use_health_environment(monkeypatch, FakeHealthEnvironment(free=2))

    assert (first, disk_free("/tmp")) == (1, 2)
