"""Отвечает тестам справкой вместо похода в сеть и помнит, о ком спрашивали."""

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import HTTP_TIMEOUT


def _silent(wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
    return {}


@dataclass
class FakeBlurbSource:
    """``answer`` вправе и ответить, и бросить, и залипнуть: источник бывает всяким.

    ``unanswered`` - про кого источник промолчал: ответ приехал неполным, и эти картины
    спрошены не были.
    """

    answer: Callable[[list[tuple[str, int | None]]], dict[tuple[str, int | None], Fact]] = _silent
    unanswered: set[tuple[str, int | None]] = field(default_factory=set)
    walks: list[list[tuple[str, int | None]]] = field(default_factory=list)

    def fetch(
        self,
        wanted: list[tuple[str, int | None]],
        timeout: float = HTTP_TIMEOUT,
        ready: Callable[[dict[tuple[str, int | None], Fact]], None] | None = None,
    ) -> tuple[dict[tuple[str, int | None], Fact], set[tuple[str, int | None]]]:
        self.walks.append(list(wanted))
        found = self.answer(list(wanted))
        if ready is not None:
            ready(found)
        return found, {key for key in wanted if key not in self.unanswered}
