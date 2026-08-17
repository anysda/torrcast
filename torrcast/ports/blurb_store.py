"""Помнит справку к меню между запусками; зовёт сценарий меню франшизы."""

from collections.abc import Iterable
from typing import Protocol

from torrcast.domain.facts.fact import Fact


class BlurbStore(Protocol):
    """Отданное :meth:`read` уже проверено на свежесть, дописывать его не надо."""

    def blurbs(
        self, wanted: list[tuple[str, int | None]]
    ) -> dict[tuple[str, int | None], Fact]: ...

    def remember(
        self,
        found: dict[tuple[str, int | None], Fact],
        misses: Iterable[tuple[str, int | None]] = (),
    ) -> None: ...
