"""Найденный приёмник: безымянный всё равно попадает в меню, и по нему есть адрес."""

from __future__ import annotations

from torrcast.adapters.chromecast.scan.device import Device


def test_a_nameless_receiver_still_gets_a_line() -> None:
    """Не представился - всё равно пункт меню: адрес у него есть, и человек его узнает.

    Пустая строка в меню была бы хуже честного «приёмник»: выбирать её человек не
    станет, а это единственный его телевизор.
    """
    assert Device("10.0.0.50").title == "receiver"
    assert Device("10.0.0.50", model="Chromecast").title == "Chromecast"
    assert Device("10.0.0.50", name="Samsung Q70D", model="Chromecast").title == "Samsung Q70D"


def test_the_maker_is_kept_even_when_the_menu_has_no_use_for_it() -> None:
    """Производитель в меню не нужен, а профиль приёмника выбирается по нему.

    У приставки Android TV имя и модель приходят пустыми, и производитель - единственное,
    чем устройство себя называет.
    """
    device = Device("10.0.0.50", maker="Xiaomi")

    assert device.maker == "Xiaomi"
    assert device.title == "receiver"


def test_the_device_is_a_value_and_not_a_mutable_record() -> None:
    """Найденное складывают в словари и множества по адресу: менять его нельзя."""
    assert len({Device("10.0.0.50"), Device("10.0.0.50")}) == 1
