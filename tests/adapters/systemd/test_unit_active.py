"""Проверяет ответ «идёт ли показ»: живым считается ровно ``active`` и ничто иное."""

from __future__ import annotations

import subprocess

import pytest

from torrcast.adapters.systemd._systemd_call import SystemdCall
from torrcast.adapters.systemd.unit_active import unit_active


def _says(answer: str) -> SystemdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, answer, "")

    return call


@pytest.mark.parametrize(
    ("answer", "alive"),
    [
        ("active\n", True),
        ("inactive\n", False),
        ("activating\n", False),
        ("failed\n", False),
        ("", False),
    ],
)
def test_only_an_active_unit_counts_as_a_running_show(answer: str, alive: bool) -> None:
    """``activating`` - ещё не показ, ``failed`` - уже не показ.

    Ответ ``systemctl`` приходит со своим переводом строки, и сравнение без очистки
    объявляло бы мёртвым любой живой показ.
    """
    assert unit_active(call=_says(answer)) is alive
