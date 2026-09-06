"""Помнит родню картин в памяти теста вместо файла на диске."""

from dataclasses import dataclass, field

from torrcast.domain.facts.kin import Kin


@dataclass
class FakeKinStore:
    """``None`` значит «не спрашивали»; записанное видно и в :attr:`written`."""

    stored: dict[str, list[Kin]] = field(default_factory=dict)
    written: list[tuple[str, list[Kin]]] = field(default_factory=list)

    def read_kin(self, entity: str) -> list[Kin] | None:
        return self.stored.get(entity)

    def write_kin(self, entity: str, found: list[Kin]) -> None:
        self.written.append((entity, found))
        self.stored[entity] = found
