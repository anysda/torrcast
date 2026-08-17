"""Отвечает тестам паспортом вместо статьи Википедии и помнит вопросы."""

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.facts.origin import Origin


def _silent(title: str, series: bool, timeout: float) -> Origin:
    return Origin()


@dataclass
class FakeArticleSource:
    """``answer`` вправе и вернуть паспорт, и бросить: молчание сети - тоже случай."""

    answer: Callable[[str, bool, float], Origin] = _silent
    calls: list[tuple[str, bool, float]] = field(default_factory=list)

    def look(self, title: str, series: bool, timeout: float) -> Origin:
        self.calls.append((title, series, timeout))
        return self.answer(title, series, timeout)
