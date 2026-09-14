"""Прокатные имена картины по её оригиналу; зовёт поиск статьи справки."""

from typing import Protocol


class RuNames(Protocol):
    """Русские прокатные имена по точной тройке «оригинал, год, тип»."""

    def ru_names(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], list[str]]: ...
