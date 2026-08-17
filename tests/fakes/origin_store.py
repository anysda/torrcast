"""Помнит паспорта картин в памяти теста вместо файла на диске."""

from dataclasses import dataclass, field

from torrcast.domain.facts.origin import Origin


@dataclass
class FakeOriginStore:
    """``None`` значит «не спрашивали»; записанное видно и в :attr:`written`."""

    stored: dict[tuple[str, bool | None], Origin] = field(default_factory=dict)
    written: list[tuple[str, bool | None, Origin]] = field(default_factory=list)

    def read(self, title: str, series: bool | None) -> Origin | None:
        return self.stored.get((title, series))

    def write(self, title: str, series: bool | None, found: Origin) -> None:
        self.written.append((title, series, found))
        self.stored[(title, series)] = found
