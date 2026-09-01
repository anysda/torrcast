"""Выбор юнита показа: платформа решает один раз, и решает обе половины сразу."""

from __future__ import annotations

import importlib
import sys

import pytest

import torrcast.runtime.show_unit as show_unit
from torrcast.adapters.launchd.launchd_show_unit import LaunchdShowUnit
from torrcast.adapters.launchd.start_play_job import start_play_job
from torrcast.adapters.systemd.start_play_unit import start_play_unit as systemd_start
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit


def test_on_linux_both_halves_are_the_systemd_ones() -> None:
    """На Linux показ играет transient-юнит systemd - ровно как до появления выбора."""
    assert type(show_unit.show_unit()) is TransientShowUnit
    assert show_unit.start_play_unit is systemd_start


def test_on_macos_both_halves_are_the_launchd_ones(monkeypatch: pytest.MonkeyPatch) -> None:
    """На macOS обе половины - launchd, и берутся из одного места.

    Разведи выбор по точкам подстановки - и половины разошлись бы молча: ``status``
    спрашивал бы systemd о задании launchd. Модуль перезагружается под чужой платформой
    и возвращается обратно, чтобы соседи по набору видели прежний выбор.
    """
    monkeypatch.setattr(sys, "platform", "darwin")
    importlib.reload(show_unit)
    try:
        assert type(show_unit.show_unit()) is LaunchdShowUnit
        assert show_unit.start_play_unit is start_play_job
    finally:
        monkeypatch.undo()
        importlib.reload(show_unit)
