"""Зеркало :mod:`torrcast.domain.unit_name`: имя юнита показа своё у каждого экземпляра."""

from __future__ import annotations

import pytest

from torrcast.domain.instance_slug import STATE_ENV
from torrcast.domain.unit_name import unit_name
from torrcast.domain.unit_naming import _UNIT_NAME


def test_the_default_instance_keeps_the_plain_unit_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Боевой экземпляр зовётся как всегда: разводка не переименовывает хозяина узла."""
    monkeypatch.delenv(STATE_ENV, raising=False)

    assert unit_name() == _UNIT_NAME


def test_a_lane_instance_gets_a_marked_unit_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """🔴 TC-1137: юнит показа - свой у каждого экземпляра узла, а не один на всех.

    Общее имя значило, что ``systemd-run`` одной полосы гасил идущий показ другой:
    запуск во вкладке снимал показ на ТВ соседнего экземпляра.
    """
    monkeypatch.setenv(STATE_ENV, "/root/полоса-а-state.json")
    first = unit_name()
    monkeypatch.setenv(STATE_ENV, "/root/полоса-б-state.json")
    second = unit_name()

    assert first != _UNIT_NAME and second != _UNIT_NAME
    assert first.startswith(_UNIT_NAME + "-") and second.startswith(_UNIT_NAME + "-")
    assert first != second
    assert not set(first) & set(" /.@\t"), "имя уезжает в systemd-run как есть"
