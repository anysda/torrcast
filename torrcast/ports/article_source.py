"""Спрашивает у справки паспорт картины по статье; зовёт сценарий паспорта."""

from typing import Protocol

from torrcast.domain.facts.origin import Origin


class ArticleSource(Protocol):
    """Синхронный поход за паспортом; неудача остаётся исключением."""

    def look(self, title: str, series: bool, timeout: float) -> Origin: ...
