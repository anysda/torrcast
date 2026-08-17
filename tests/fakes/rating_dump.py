"""Отдаёт тестам оценки и голоса IMDb из памяти вместо выгрузки на диске."""

from collections.abc import Callable
from dataclasses import dataclass, field


def _nothing() -> dict[str, str]:
    return {}


@dataclass
class FakeRatingDump:
    """``scores`` подменяется целиком: им проверяют, когда выгрузку читают."""

    scores: Callable[[], dict[str, str]] = _nothing
    counted: dict[str, int] = field(default_factory=dict)
    asked: list[str] = field(default_factory=list)

    def votes(self) -> dict[str, int]:
        self.asked.append("votes")
        return self.counted
