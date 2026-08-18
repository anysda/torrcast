"""Кто такой приёмник на том конце: профиль по ключу из настроек или по паспорту.

Правила выбора - в :mod:`torrcast.domain.profile` и :func:`torrcast.domain.for_passport`,
а здесь то, чего домену нельзя: опрос живого устройства (:func:`torrcast.adapters.
chromecast.scan.named`) и память о нём. Ответ кэшируется на процесс - показ спрашивает
профиль в нескольких местах, а выключенный ТВ стоит секунд на каждом.

Экземпляр :data:`detector` один на процесс, и спрашивают профиль у него же и показ,
и `cast doctor`, и снимок порогов для ленты: кэш паспортов у всех общий.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from torrcast.domain.by_key import by_key
from torrcast.domain.choice import Choice
from torrcast.domain.for_passport import for_passport
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.health_config import HealthConfig

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.scan.device import Device

#: Сколько ждём паспорт приёмника: он отвечает мгновенно или не отвечает вовсе.
PASSPORT_TIMEOUT: Final = 2.0


class ProfileDetector:
    """Профиль приёмника с памятью на адрес: спрашиваем устройство один раз на процесс."""

    def __init__(
        self,
        timeout: float = PASSPORT_TIMEOUT,
        ask: Callable[..., Device] | None = None,
    ) -> None:
        self._seen: dict[str, Choice] = {}
        self._timeout = timeout
        self._ask = ask

    def detect(self, config: HealthConfig) -> Choice:
        """Выбрать профиль: ручной ключ, затем сохранённый или опрошенный паспорт."""
        named = str(getattr(config, "receiver_profile", "") or "")
        if named:
            chosen = by_key(named)
            if chosen is not None:
                return Choice(chosen, f"назван руками: receiver_profile={chosen.key}")
            return Choice(CAUTIOUS, f"профиля «{named}» нет - беру осторожный")
        address = str(config.tv or "")
        if config.receiver != "chromecast" or not address:
            return Choice(CAUTIOUS, "приёмника с паспортом нет - беру осторожный")
        if address not in self._seen:
            self._seen[address] = self._asked(address)
        return self._seen[address]

    def forget(self) -> None:
        """Очистить кэш паспортов приёмников."""
        self._seen.clear()

    def _asked(self, address: str) -> Choice:
        """Спросить паспорт у самого устройства. Молчание - осторожный профиль, не авария.

        Кем спрашивать, знает либо тот, кто завёл прибор, либо умолчание - штатный опрос
        (:func:`torrcast.adapters.chromecast.scan.named`). Импорт умолчания ленивый: сеть
        стоит секунд на импорте, а профиль спрашивают и там, где до неё не дойдёт.
        """
        ask = self._ask if self._ask is not None else self._named()

        try:
            device = ask(address, timeout=self._timeout)
        except Exception:
            return Choice(CAUTIOUS, "приёмник не ответил - беру осторожный")
        passport = ", ".join(part for part in (device.maker, device.model, device.name) if part)
        if not passport:
            return Choice(CAUTIOUS, "приёмник не представился - беру осторожный")
        return Choice(
            for_passport(device.maker, device.model, device.name), f"по паспорту: {passport}"
        )

    @staticmethod
    def _named() -> Callable[..., Device]:
        """Штатный опрос устройства; берётся в момент вопроса, а не на импорте модуля."""
        from torrcast.adapters.chromecast.scan.named import named

        return named


#: Один кэш на процесс: и показ, и ``cast doctor`` спрашивают профиль у него же.
detector: Final = ProfileDetector()
