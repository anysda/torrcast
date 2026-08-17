"""Слот консольного порта: правило спрашивает того, кого поставил корень."""

from __future__ import annotations

from importlib import import_module

import pytest

from tests.fakes.console import FakeConsole
from torrcast.usecases.rank.configure import _console_port, configure

#: ⚠️ Модулем, а не атрибутом пакета: у пакета имя `configure` занято одноимённой
#: единицей, и подмена на функции ставится в никуда - молча.
_slot = import_module("torrcast.usecases.rank.configure")


def test_the_slot_hands_over_exactly_what_the_root_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без этого слота вопрос про озвучку уходил бы в пустоту: порт тут один на пакет."""
    fake = FakeConsole()
    monkeypatch.setattr(_slot, "_console", None, raising=False)

    configure(fake)

    assert _console_port() is fake


def test_a_second_call_replaces_the_port_and_does_not_add_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Слот один: пересборка окружения обязана заменить порт, а не завести второй."""
    first, second = FakeConsole(), FakeConsole()
    monkeypatch.setattr(_slot, "_console", None, raising=False)

    configure(first)
    configure(second)

    assert _console_port() is second
