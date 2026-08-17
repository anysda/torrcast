"""Помнит справку к меню в памяти теста вместо файла на диске."""

from collections.abc import Iterable
from dataclasses import dataclass, field

from torrcast.domain.facts.fact import Fact


@dataclass
class FakeBlurbStore:
    """Отданное :meth:`blurbs` уже считается свежим: политику срока проверяют правила."""

    stored: dict[tuple[str, int | None], Fact] = field(default_factory=dict)
    remembered: list[tuple[dict[tuple[str, int | None], Fact], list[tuple[str, int | None]]]] = (
        field(default_factory=list)
    )

    def blurbs(self, wanted: list[tuple[str, int | None]]) -> dict[tuple[str, int | None], Fact]:
        return {key: self.stored[key] for key in wanted if key in self.stored}

    def remember(
        self,
        found: dict[tuple[str, int | None], Fact],
        misses: Iterable[tuple[str, int | None]] = (),
    ) -> None:
        blanks = list(misses)
        self.remembered.append((dict(found), blanks))
        self.stored.update(found)
        self.stored.update({key: Fact() for key in blanks})
