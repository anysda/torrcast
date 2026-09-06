"""Отвечает тестам родней картины вместо Wikidata и помнит, о чём спрашивали."""

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.facts.kin import Kin


def _empty(entity: str, timeout: float) -> list[Kin]:
    return []


@dataclass
class FakeKinSource:
    """``asked`` пуст - значит Wikidata за родней не звали, и это проверяется."""

    answer: Callable[[str, float], list[Kin]] = _empty
    asked: list[str] = field(default_factory=list)

    def kin(self, entity: str, timeout: float) -> list[Kin]:
        self.asked.append(entity)
        return self.answer(entity, timeout)
