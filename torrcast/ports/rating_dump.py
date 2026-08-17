"""Читает офлайн-выгрузку оценок IMDb; зовут добор справки и офлайн-карта имён."""

from typing import Protocol


class RatingDump(Protocol):
    """Нет файла - пустые словари, и это не сбой: рейтинга просто не будет."""

    def scores(self) -> dict[str, str]: ...

    def votes(self) -> dict[str, int]: ...
