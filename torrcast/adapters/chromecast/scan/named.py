"""Имя и модель устройства по адресу - опросом самого устройства, без единой команды.

Спрашивает их поиск приёмников для найденных обходом и определение профиля."""

from __future__ import annotations

from contextlib import suppress
from typing import Final

from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise
from torrcast.adapters.chromecast.scan.device import Device

#: Сколько ждём ответа на опрос имени: имя - украшение, ради него ждать некогда.
NAME_TIMEOUT: Final = 3.0


def named(address: str, timeout: float = NAME_TIMEOUT) -> Device:
    """Имя и модель устройства по адресу - опросом самого устройства, без единой команды.

    Спрашиваем ``pychromecast`` - тот же опрос, каким он сам разбирает найденные по
    адресу устройства: обычный HTTP к странице сведений. Ни соединения показа, ни
    ``LOAD``, ни пультовых команд здесь нет и быть не должно - обнаружение не имеет
    права трогать чужой экран.

    Устройство не представилось (не отвечает, отвечает не так) - возвращаем пункт без
    имени: адрес у него всё равно есть, и в меню он попадёт.
    """
    try:
        from pychromecast.dial import get_device_info
    except ImportError:  # pragma: no cover - pychromecast стоит зависимостью
        return Device(address=address, how="скан")
    # Опрос устройства идёт и по 8443, которого у телевизора нет: жалоба на это -
    # косметика, а поиск и без неё честно скажет, что нашёл (:class:`torrcast.cast._Cosmetic`).
    hush_cosmetic_noise()
    status = None
    with suppress(Exception):
        status = get_device_info(address, timeout=timeout)
    if status is None:
        return Device(address=address, how="скан")
    return Device(
        address=address,
        name=str(status.friendly_name or ""),
        model=str(status.model_name or ""),
        how="скан",
        maker=str(getattr(status, "manufacturer", "") or ""),
    )
