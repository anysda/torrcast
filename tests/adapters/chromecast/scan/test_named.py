"""Опрос имени по адресу: обнаружение не имеет права трогать чужой экран."""

from __future__ import annotations

import logging

import pytest

from torrcast.adapters.chromecast.scan.named import NAME_TIMEOUT, named


class _Status:
    friendly_name = "Samsung Q70D"
    model_name = "SAMSUNG"
    manufacturer = "Samsung"


def test_the_device_tells_its_name_and_maker_over_plain_http(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Спрашиваем страницу сведений - и ничего больше: ни LOAD, ни пультовых команд.

    Обнаружение, которое запускает что-то на чужом экране, - это не обнаружение.
    """
    asked: list[tuple[str, float]] = []

    def info(address: str, timeout: float = 0.0) -> _Status:
        asked.append((address, timeout))
        return _Status()

    monkeypatch.setattr("pychromecast.dial.get_device_info", info)

    device = named("10.0.0.50", timeout=1.5)

    assert asked == [("10.0.0.50", 1.5)]
    assert device.name == "Samsung Q70D"
    assert device.model == "SAMSUNG"
    assert device.maker == "Samsung"
    assert device.how == "скан", "нашёл его обход, а не mDNS - это видно в меню"


def test_a_device_that_did_not_answer_still_becomes_a_menu_line(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Не представился - остаётся пунктом без имени: адрес у него всё равно есть."""

    def refuse(_address: str, timeout: float = 0.0) -> object:
        raise OSError("не отвечает")

    monkeypatch.setattr("pychromecast.dial.get_device_info", refuse)

    device = named("10.0.0.50")

    assert device.address == "10.0.0.50"
    assert device.name == "" and device.model == ""
    assert device.how == "скан"


def test_a_device_that_answered_with_nothing_is_the_same_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пустой ответ - это тоже «не представился», а не приёмник с именем ``None``."""
    monkeypatch.setattr("pychromecast.dial.get_device_info", lambda _a, timeout=0.0: None)

    assert named("10.0.0.50").title == "receiver"


def test_the_cosmetic_complaint_is_hushed_before_the_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Опрос идёт и по 8443, которого у телевизора нет: жалоба на это - косметика.

    Не приглуши её - и на каждый адрес подсети в вывод падала бы строка, стоившая
    когда-то ложной гипотезы «телевизор выпадает по 8009».
    """
    logger = logging.getLogger("pychromecast.dial")
    monkeypatch.setattr(logger, "filters", [])
    monkeypatch.setattr("pychromecast.dial.get_device_info", lambda _a, timeout=0.0: _Status())

    named("10.0.0.50")

    noise = logging.LogRecord("pychromecast.dial", logging.WARNING, __file__, 1, None, None, None)
    noise.msg = "Failed to determine cast type for host 10.0.0.50"
    assert logger.filters, "жалоба 8443 не приглушена - строка полетит на каждый адрес"
    assert not logger.filter(noise), "приглушена именно эта строка, а не логгер целиком"

    real = logging.LogRecord("pychromecast.dial", logging.WARNING, __file__, 1, None, None, None)
    real.msg = "Failed to connect to service"
    assert logger.filter(real), "настоящие жалобы обязаны доходить до человека"


def test_the_patience_for_a_name_is_short_because_a_name_is_a_decoration() -> None:
    """Имя - украшение, ради него ждать некогда: без него пункт меню всё равно будет."""
    assert NAME_TIMEOUT == 3.0
