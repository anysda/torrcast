"""Помнит паспорта картин между запусками; зовёт сценарий паспорта."""

from typing import Protocol

from torrcast.domain.facts.origin import Origin


class OriginStore(Protocol):
    """``None`` от :meth:`read` значит «не спрашивали», пустой паспорт - «нет его»."""

    def read(self, title: str, series: bool | None) -> Origin | None: ...

    def write(self, title: str, series: bool | None, found: Origin) -> None: ...
