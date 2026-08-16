"""Ищет для сценариев раздачи во внешнем каталоге торрентов."""

from typing import Protocol

from torrcast.domain.release import Release


class TorrentIndex(Protocol):
    def search(self, query: str) -> list[Release]: ...
