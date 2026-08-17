"""Отвечает тестам паспортом вместо офлайн-карты имён и помнит вопросы."""

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.facts.origin import Origin


def _silent(title: str, series: bool) -> Origin:
    return Origin()


@dataclass
class FakeNameCatalogue:
    """``asked`` пуст - значит в карту не ходили вовсе, и это проверяемое свойство."""

    answer: Callable[[str, bool], Origin] = _silent
    asked: list[str] = field(default_factory=list)

    def look(self, title: str, series: bool) -> Origin:
        self.asked.append(title)
        return self.answer(title, series)
