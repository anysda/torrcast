"""Выбор профиля приёмника: ключ руками, паспорт устройства и память на адрес."""

from __future__ import annotations

from torrcast.adapters.chromecast.profile_detector import ProfileDetector
from torrcast.adapters.chromecast.scan.device import Device
from torrcast.domain.config import Config
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS


def test_a_named_key_is_the_last_word() -> None:
    """Ключ в настройках перебивает паспорт и устройство не спрашивает вовсе."""
    chosen = ProfileDetector().detect(Config(tv="10.0.0.50", receiver_profile="androidtv"))
    assert chosen.profile is ANDROID_TV and "руками" in chosen.how


def test_an_unknown_name_in_the_config_is_not_a_crash() -> None:
    """Опечатка в ``receiver_profile`` - осторожный профиль и честная строка, а не отказ."""
    chosen = ProfileDetector().detect(Config(tv="10.0.0.50", receiver_profile="q70"))

    assert chosen.profile is CAUTIOUS and "q70" in chosen.how


def test_without_an_address_nobody_is_asked() -> None:
    """Без адреса ТВ спрашивать не у кого - осторожный профиль, а не поход в сеть."""

    def refuse(address: str, timeout: float = 0.0) -> Device:
        raise AssertionError("паспорт спрашивать было не у кого")

    assert ProfileDetector(ask=refuse).detect(Config()).profile is CAUTIOUS


def test_a_receiver_without_a_passport_is_not_asked_either() -> None:
    """Заглушка показа паспорта не отдаёт: у неё и адрес свой, и спрашивать некого."""

    def refuse(address: str, timeout: float = 0.0) -> Device:
        raise AssertionError("паспорт спрашивать было не у кого")

    detector = ProfileDetector(ask=refuse)

    assert detector.detect(Config(tv="mock", receiver="mock")).profile is CAUTIOUS


def test_the_passport_is_asked_once_per_address() -> None:
    """Паспорт спрашивается один раз на адрес: показ зовёт профиль в нескольких местах."""
    asked: list[str] = []

    def once(address: str, timeout: float = 0.0) -> Device:
        asked.append(address)
        return Device(address=address, maker="Xiaomi")

    detector = ProfileDetector(ask=once)
    config = Config(tv="10.0.0.50")
    assert detector.detect(config).profile is ANDROID_TV
    assert detector.detect(config).profile is ANDROID_TV
    assert asked == ["10.0.0.50"], "второй раз устройство не дёргаем"
    detector.forget()
    assert detector.detect(config).profile is ANDROID_TV
    assert asked == ["10.0.0.50", "10.0.0.50"], "после forget спрашиваем заново"


def test_a_silent_receiver_gets_the_cautious_profile() -> None:
    """Приёмник не ответил (спит, сети нет) - осторожный профиль, а не авария показа."""

    def dead(address: str, timeout: float = 0.0) -> Device:
        raise OSError("сети нет")

    chosen = ProfileDetector(ask=dead).detect(Config(tv="10.0.0.50"))
    assert chosen.profile is CAUTIOUS and "не ответил" in chosen.how
