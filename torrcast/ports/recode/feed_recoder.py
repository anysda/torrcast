"""Кодировщик тяжёлых кусков в объёме, в каком его знает лента показа."""

from pathlib import Path
from typing import Protocol

from torrcast.ports.recode.encoding_rate import EncodingRate
from torrcast.ports.recode.recode_pace import RecodePace


class FeedRecoder(Protocol):
    """Что лента показа спрашивает у кодировщика - и ничего сверх того.

    Лента кодировщиком не распоряжается: очередь, порог тяжести и подъём потока - дело
    самого кодировщика и того, кто его собрал (показ). Ленте он нужен ровно на трёх
    поворотах: отдать готовый перекод вместо тяжёлой копии, придержать копию, пока
    перекод считается, и ужать кусок на месте, когда ждать больше нечего.
    """

    #: Каталог перекодированных кусков и его же корень для ужатия на месте.
    spare: Path
    #: Потолок ожидания перекода, секунды: тот же, что у предохранителя кодировщика.
    over_wait: float
    #: Где идёт показ, секунды фильма: по нему кодировщик решает, за что браться.
    played: float
    #: Слоты, за которые кодировщику браться уже незачем.
    done: set[int]

    @property
    def pace(self) -> RecodePace: ...

    def stop(self) -> None: ...
    def opening(self, slot: int) -> None: ...
    def note(self, slot: int, how: str) -> None: ...
    def holding(self, slot: int, size: int = 0) -> bool: ...
    def ready(self, slot: int) -> Path | None: ...
    def fit(self, span: float, preset: str) -> EncodingRate: ...
