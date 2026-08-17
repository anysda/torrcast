"""Проверяет, что ключ играющего показа достаётся из описания юнита и только оттуда."""

from __future__ import annotations

import subprocess

import pytest

from torrcast.adapters.systemd import unit_key as module
from torrcast.domain.unit_naming import _UNIT_TAG


def _says(answer: str) -> object:
    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, answer, "")

    return call


def test_the_key_of_the_playing_show_comes_from_its_own_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Свежайшая запись в state для этого не годится: рядом мог писать другой ход.

    Метка юнита снимается целиком, а не «первое слово»: ключ бывает с дефисами и
    пробелами внутри.
    """
    monkeypatch.setattr(module, "_systemd", _says(f"{_UNIT_TAG}моана 2\n"))
    assert module.unit_key() == "моана 2"


def test_a_description_that_is_not_ours_gives_no_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чужое описание и пустой ответ - не ключ: показа с таким именем мы не заводили."""
    monkeypatch.setattr(module, "_systemd", _says("чужой юнит\n"))
    assert module.unit_key() == ""
    monkeypatch.setattr(module, "_systemd", _says(""))
    assert module.unit_key() == ""
