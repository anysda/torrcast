"""Отвечает тестам годом первой публикации вместо Wikidata и помнит вопросы."""

from collections.abc import Callable
from dataclasses import dataclass, field


def _silent(entity: str, timeout: float) -> int | None:
    return None


@dataclass
class FakeDateSource:
    """``asked`` пуст - значит второй источник не спрашивали, и это проверяется."""

    answer: Callable[[str, float], int | None] = _silent
    asked: list[str] = field(default_factory=list)

    def published(self, entity: str, timeout: float) -> int | None:
        self.asked.append(entity)
        return self.answer(entity, timeout)
