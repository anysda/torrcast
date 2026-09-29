"""Каталог сериала: номера серий и даты выхода; зовут плашка следующей серии и цикл юнита."""

from collections.abc import Callable, Mapping
from typing import Protocol

from torrcast.ports.aired_state import AiredState

#: Серии сериала с датами выхода и достоверность ответа TVmaze.
Aired = tuple[Mapping[tuple[int, int], tuple[str, str]], AiredState]


class SeriesSource(Protocol):
    """IMDb-id по карте имён, номера серий по индексу IMDb, даты выхода по TVmaze, часы."""

    @property
    def ids(self) -> Callable[[str, str, int | None], str]:
        """IMDb-id по названию, оригиналу и году; пустая строка - не узнан."""

    @property
    def numbers(self) -> Callable[[str], Mapping[int, tuple[int, ...]] | None]:
        """Номера серий по сезонам из индекса IMDb."""

    @property
    def aired(self) -> Callable[[str, float], Aired]:
        """Даты выхода серий по TVmaze; ``UNKNOWN`` - сеть или фоновый вопрос."""

    @property
    def now(self) -> Callable[[], str]:
        """Текущий момент ISO с поясом."""
