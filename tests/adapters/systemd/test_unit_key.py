"""Проверяет, что ключ играющего показа достаётся из описания юнита и только оттуда."""

from __future__ import annotations

import subprocess

from torrcast.adapters.systemd._systemd_call import SystemdCall
from torrcast.adapters.systemd.unit_key import unit_key
from torrcast.domain.unit_naming import _UNIT_TAG


def _says(answer: str) -> SystemdCall:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, answer, "")

    return call


def test_the_key_of_the_playing_show_comes_from_its_own_description() -> None:
    """Свежайшая запись в state для этого не годится: рядом мог писать другой ход.

    Метка юнита снимается целиком, а не «первое слово»: ключ бывает с дефисами и
    пробелами внутри.
    """
    assert unit_key(call=_says(f"{_UNIT_TAG}моана 2\n")) == "моана 2"


def test_a_description_that_is_not_ours_gives_no_key() -> None:
    """Чужое описание и пустой ответ - не ключ: показа с таким именем мы не заводили."""
    assert unit_key(call=_says("чужой юнит\n")) == ""
    assert unit_key(call=_says("")) == ""
