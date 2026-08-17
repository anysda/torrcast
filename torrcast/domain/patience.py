"""Терпение приёмника к стоящей картинке: когда перезабрать кусок и когда бросить показ."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Patience:
    """Сколько приёмник терпит стоящую картинку и сколько раз перезаберёт кусок сам.

    Оба числа приходят из профиля приёмника (:mod:`torrcast.domain.profile`): у одного
    аппарата медиасессия живёт секунды и перезаборы есть, у другого их нет вовсе.
    """

    seconds: float
    retries: int

    def gave_up(self, dark: float) -> bool:
        """Терпение кончилось: медиасессии больше нет, и позиции в ней тоже."""
        return dark >= self.seconds

    def retry_due(self, dark: float, spent: int) -> bool:
        """Пора ли перезабрать кусок: попытки разнесены по терпению поровну.

        ⚠️ Перезабор - не повтор LOAD: медиасессия та же, приёмник переспрашивает по HTTP
        тот же кусок. Источник к этому моменту может вернуться, и тогда картинка пойдёт
        дальше без всякого воскрешения.
        """
        step = self.seconds / (self.retries + 1)
        return spent < self.retries and dark >= step * (spent + 1)
