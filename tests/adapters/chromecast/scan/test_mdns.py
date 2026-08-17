"""Итог слушания mDNS: пустой список без причины однажды уже родил ложную тревогу."""

from __future__ import annotations

import dataclasses

import pytest

from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.chromecast.scan.mdns import Mdns


def test_a_heard_receiver_comes_without_a_reason() -> None:
    """Услышали - причине взяться неоткуда: она про то, почему НЕ услышали."""
    heard = Mdns(devices=[Device("10.0.0.50", name="Samsung Q70D", how="mdns")])

    assert heard.reason == ""
    assert heard.note == ""


def test_the_reason_is_read_by_the_machine_and_the_note_by_a_human() -> None:
    """Две разные вещи в одном итоге: ``reason`` разбирает doctor, ``note`` печатается.

    Слей их в одну строку - и щуп служб разбирал бы человеческий текст, а человек читал
    бы «module».
    """
    silent = Mdns(reason="module", note="mDNS не слушаю: в этом python нет модуля zeroconf")

    assert silent.devices == []
    assert silent.reason == "module"
    assert "zeroconf" in silent.note


def test_each_result_gets_its_own_list_of_devices() -> None:
    """Два слушания подряд не имеют права делить один список найденного."""
    first, second = Mdns(), Mdns()
    first.devices.append(Device("10.0.0.50"))

    assert second.devices == []


def test_the_result_of_a_listening_is_a_value_and_not_a_record_to_edit() -> None:
    """Итог слушания читают поиск и щуп служб - править его по дороге нельзя никому."""
    heard = Mdns(reason="silence", note="никто не отозвался")

    with pytest.raises(dataclasses.FrozenInstanceError):
        heard.reason = "network"  # type: ignore[misc]
