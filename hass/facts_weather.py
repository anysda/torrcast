"""Погода источника картинок: был ли 429 или отказ по счёту и когда тишина кончится.

Её спрашивает приговор находок (:class:`hass.hit_posters.HitPosters`): пустой ответ в
минуту отказов не значит «картинки нет», и пятиминутный промах за него не пишется.
"""

from __future__ import annotations

import time
from typing import Protocol

from torrcast.runtime.facts_wiring import FACTS


class _Weather(Protocol):
    """Отказы источника на часах монотонного времени процесса."""

    def troubled_since(self, moment: float) -> bool: ...

    def calm_at(self) -> float: ...


class FactsWeather:
    """Погода общего клиента справки; клиент без счёта отказов всегда спокоен."""

    def troubled_since(self, moment: float) -> bool:
        told = getattr(FACTS.client, "troubled_since", None)
        return bool(told(moment)) if callable(told) else False

    def calm_at(self) -> float:
        told = getattr(FACTS.client, "calm_at", None)
        return float(told()) if callable(told) else time.monotonic()


class _CalmWeather:
    """Источник-подделка: отказов не бывает, спрашивать можно сразу."""

    def troubled_since(self, moment: float) -> bool:
        return moment < float("-inf")

    def calm_at(self) -> float:
        return float("-inf")


__all__ = ["FactsWeather"]
