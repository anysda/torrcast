"""Сверяет картину с IMDb-id по офлайн-карте имён; зовёт справка меню."""

from typing import Protocol


class TitleIds(Protocol):
    """Точная локальная пара имени, года и типа с IMDb."""

    def ids(
        self, pictures: list[tuple[str, int | None, str]]
    ) -> dict[tuple[str, int | None], str]: ...
