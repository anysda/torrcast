"""Второй источник года картины; зовёт сценарий паспорта на одиноком ответе."""

from typing import Protocol


class DateSource(Protocol):
    """Год первой публикации; нет даты или источник молчит - ``None``."""

    def published(self, entity: str, timeout: float) -> int | None: ...
