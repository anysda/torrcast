"""Внешние службы, нужные сценарию уточнения каталога."""

from typing import Any, Protocol


class ReinforceEnvironment(Protocol):
    """Предоставляет справку, поиск и телеметрию без знания адаптеров."""

    @property
    def fact_type(self) -> Any: ...
    @property
    def prowlarr_type(self) -> Any: ...

    origin: Any
    minutes_of: Any
    same_name: Any
    merge: Any
    to_releases: Any
    trace: Any
