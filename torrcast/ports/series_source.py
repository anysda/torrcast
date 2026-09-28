"""Каталог сериала: номера серий и даты выхода; зовут плашка следующей серии и цикл юнита."""

from collections.abc import Callable, Mapping
from typing import Protocol

#: Серии сериала с датами выхода: ``(сезон, серия) -> (момент ISO, день)``, и «ещё в пути».
Aired = tuple[Mapping[tuple[int, int], tuple[str, str]], bool]


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
        """Даты выхода серий по TVmaze; пусто - дат нет."""

    @property
    def now(self) -> Callable[[], str]:
        """Текущий момент ISO с поясом."""
