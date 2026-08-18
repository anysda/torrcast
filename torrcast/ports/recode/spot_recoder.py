"""Кодировщик тяжёлых кусков целиком: договор того, кто его поднимает и раздаёт."""

from typing import Protocol

from torrcast.ports.recode.feed_recoder import FeedRecoder
from torrcast.ports.recode.spot_rival import SpotRival


class SpotRecoder(FeedRecoder, SpotRival, Protocol):
    """Фоновый перекод тяжёлых слотов: всё, что о нём знает показ.

    Кодировщик у показа один, а спрашивают его трое, и спрашивают РАЗНОЕ: лента берёт у
    него готовые куски (:class:`~torrcast.ports.recode.feed_recoder.FeedRecoder`), сборка
    прогрева - слоты и решение (:class:`~torrcast.ports.recode.spot_rival.SpotRival`), сам
    прогрев - только признак захода
    (:class:`~torrcast.ports.recode.recode_rival.RecodeRival`). Отсюда и наследование:
    широкий договор держит тот, кто кодировщика собрал и раздал, а каждому потребителю
    достаётся его доля - и подходит она ему целиком, без приведений на границе.

    Поднять поток умеет только этот, самый широкий договор: решение «работать или нет»
    принимает тот же, кто кодировщика создал.
    """

    def start(self) -> None:
        """Поднять поток кодировщика; тяжёлых кусков нет - он не поднимается вовсе."""
