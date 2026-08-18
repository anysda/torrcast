"""Проверяет, что погашение показа зовёт именно остановку юнита и именно того юнита."""

from __future__ import annotations

import subprocess

from torrcast.adapters.systemd._systemd_call import SystemdCall
from torrcast.adapters.systemd.stop_play_unit import stop_play_unit
from torrcast.domain.unit_naming import _UNIT_NAME


def _remember(seen: list[tuple[str, ...]]) -> SystemdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        seen.append((tool, *args))
        return subprocess.CompletedProcess([tool, *args], 0, "", "")

    return call


def test_stopping_the_show_waits_for_the_unit_to_die() -> None:
    """``systemctl stop`` не возвращается, пока юнит жив, - на этом держится дозапись позиции.

    По SIGTERM сторож показа дописывает позицию в state; замени ``stop`` на ``kill`` или
    на асинхронный ``--no-block``, и продолжение с середины потеряет последние минуты.
    """
    seen: list[tuple[str, ...]] = []
    stop_play_unit(call=_remember(seen))

    assert seen == [("systemctl", "stop", _UNIT_NAME)]


def test_the_unit_name_can_be_named_from_outside() -> None:
    """Имя юнита - аргумент с умолчанием: щупы гасят свой юнит, а не показ человека."""
    seen: list[tuple[str, ...]] = []
    stop_play_unit("torrcast-проба", call=_remember(seen))

    assert seen == [("systemctl", "stop", "torrcast-проба")]
