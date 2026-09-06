"""Помнит родню картины между запусками; зовёт сценарий полки франшизы."""

from typing import Protocol

from torrcast.domain.facts.kin import Kin


class KinStore(Protocol):
    """``None`` от :meth:`read_kin` значит «не спрашивали», пустой список - «родни нет»."""

    def read_kin(self, entity: str) -> list[Kin] | None: ...

    def write_kin(self, entity: str, found: list[Kin]) -> None: ...
