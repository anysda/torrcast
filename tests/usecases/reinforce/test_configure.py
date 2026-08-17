"""Слоты каталога раздач и справки: круги добора спрашивают того, кого поставил корень."""

from __future__ import annotations

from importlib import import_module

import pytest

from tests.fakes.passport import FakePassport
from tests.usecases.reinforce.stand import Catalogue
from torrcast.usecases.reinforce.configure import _catalogue_port, _passport_port, configure

#: ⚠️ Модулем, а не атрибутом пакета: у пакета имя `configure` занято одноимённой
#: единицей, и подмена на функции ставится в никуда - молча.
_slot = import_module("torrcast.usecases.reinforce.configure")


def test_the_slots_hand_over_exactly_what_the_root_installed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Без них круг добора уходил бы в пустоту: каталог и справка тут одни на пакет."""
    catalogue, passport = Catalogue(), FakePassport()
    monkeypatch.setattr(_slot, "_catalogue", None, raising=False)
    monkeypatch.setattr(_slot, "_passport_source", None, raising=False)

    configure(catalogue, passport)

    assert _catalogue_port() is catalogue
    assert _passport_port() is passport


def test_a_second_call_replaces_the_ports_and_does_not_add_any(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Слот один: пересборка окружения обязана заменить порты, а не завести вторые."""
    monkeypatch.setattr(_slot, "_catalogue", None, raising=False)
    monkeypatch.setattr(_slot, "_passport_source", None, raising=False)
    first, second = Catalogue(), Catalogue()

    configure(first, FakePassport())
    configure(second, FakePassport())

    assert _catalogue_port() is second
