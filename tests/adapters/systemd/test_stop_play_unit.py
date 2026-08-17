"""Проверяет, что погашение показа зовёт именно остановку юнита и именно того юнита."""

from __future__ import annotations

import subprocess

import pytest

from torrcast.adapters.systemd import stop_play_unit as module
from torrcast.domain.unit_naming import _UNIT_NAME


def _remember(seen: list[tuple[str, ...]]) -> object:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], 0, "", "")

    return call


def test_stopping_the_show_waits_for_the_unit_to_die(monkeypatch: pytest.MonkeyPatch) -> None:
    """``systemctl stop`` не возвращается, пока юнит жив, - на этом держится дозапись позиции.

    По SIGTERM сторож показа дописывает позицию в state; замени ``stop`` на ``kill`` или
    на асинхронный ``--no-block``, и продолжение с середины потеряет последние минуты.
    """
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(module, "_systemd", _remember(seen))
    module.stop_play_unit()

    assert seen == [("systemctl", "stop", _UNIT_NAME)]


def test_the_unit_name_can_be_named_from_outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Имя юнита - аргумент с умолчанием: щупы гасят свой юнит, а не показ человека."""
    seen: list[tuple[str, ...]] = []
    monkeypatch.setattr(module, "_systemd", _remember(seen))
    module.stop_play_unit("torrcast-проба")

    assert seen == [("systemctl", "stop", "torrcast-проба")]
