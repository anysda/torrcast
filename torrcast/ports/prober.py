"""Читает для сценариев паспорт медиапотока."""

from typing import Protocol

from torrcast.domain.media import Media


class Prober(Protocol):
    def probe(self, source_url: str) -> Media: ...
