"""Итог поиска: приёмники и строки о том, чего мы не смотрели."""

from __future__ import annotations

from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.chromecast.scan.found import Found


def test_an_empty_search_is_an_empty_result_and_not_a_shared_one() -> None:
    """Два поиска подряд не имеют права делить один список: списки заводятся свои."""
    first, second = Found(), Found()
    first.devices.append(Device("10.0.0.50"))

    assert second.devices == []
    assert second.notes == []


def test_what_was_not_looked_at_travels_with_what_was_found() -> None:
    """Пропущенное едет рядом с найденным: человеку надо сказать о нём вслух.

    Отдай поиск один список приёмников - и «телевизор не нашёлся» было бы не отличить
    от «его подсеть я даже не смотрел».
    """
    found = Found(devices=[Device("10.0.0.50")], notes=["слишком большие подсети не обхожу"])

    assert [device.address for device in found.devices] == ["10.0.0.50"]
    assert found.notes == ["слишком большие подсети не обхожу"]
