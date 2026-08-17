"""Зеркало :mod:`torrcast.adapters.systemd.transient_show_unit`: показ как объект за портом.

Своего кода у адаптера нет ни строчки: он только называет разговор с systemd именами
договора. Поэтому сторожится ровно две вещи - что каждое имя договора ведёт к СВОЕЙ
системной операции (перепутай их - ``status`` начнёт гасить показ вместо опроса), и что
наружу уходит тип договора, а не то, что вернула система.
"""

from __future__ import annotations

from typing import Any

import pytest

from torrcast.adapters.systemd import transient_show_unit as adapter
from torrcast.adapters.systemd.transient_show_unit import TransientShowUnit
from torrcast.ports.show_unit import ShowUnit


def test_the_adapter_is_the_port_the_rest_of_the_show_talks_to() -> None:
    """Сценарии зовут показ по договору, а не по этому классу.

    Разойдись адаптер с портом хоть одним именем - подмена на подделку в тестах и на
    настоящий юнит в бою перестала бы быть взаимозаменяемой, и разошлись бы они молча.
    """
    unit: ShowUnit = TransientShowUnit()
    contract = {name for name in vars(ShowUnit) if not name.startswith("_")}

    assert contract
    assert contract <= {name for name in dir(unit) if not name.startswith("_")}


def test_every_name_of_the_contract_leads_to_its_own_system_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Четыре имени договора - четыре разные операции, и перепутать их нельзя.

    Опрос, чтение причины, чтение ключа и гашение - разные по цене и по последствиям:
    свяжись «идёт ли показ» с гашением, и обычный ``status`` убивал бы картину на экране.
    """
    called: list[str] = []

    def spy(name: str, answer: Any) -> Any:
        def _call() -> Any:
            called.append(name)
            return answer

        return _call

    monkeypatch.setattr(adapter, "unit_active", spy("active", True))
    monkeypatch.setattr(adapter, "unit_why", spy("why", "рой замолчал"))
    monkeypatch.setattr(adapter, "unit_key", spy("key", "movie:кино:2020"))
    monkeypatch.setattr(adapter, "stop_play_unit", spy("stop", None))

    unit = TransientShowUnit()

    assert unit.active() is True
    assert unit.why() == "рой замолчал"
    assert unit.key() == "movie:кино:2020"
    unit.stop()
    assert called == ["active", "why", "key", "stop"]


def test_the_answer_carries_the_type_of_the_contract_and_not_of_the_system(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Молчание systemd приводится к типу договора, а не течёт наружу как есть.

    Погашенный юнит не отвечает ни причиной, ни ключом. Уйди наружу пустота вместо строки -
    первый же, кто сложит её с другой строкой или спросит её длину, упал бы на состоянии,
    которое случается штатно после каждого показа.
    """
    monkeypatch.setattr(adapter, "unit_active", lambda: None)
    monkeypatch.setattr(adapter, "unit_why", lambda: None)
    monkeypatch.setattr(adapter, "unit_key", lambda: None)

    unit = TransientShowUnit()

    assert unit.active() is False
    assert isinstance(unit.why(), str)
    assert isinstance(unit.key(), str)
