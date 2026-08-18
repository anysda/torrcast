"""Ищет для сценариев раздачи во внешнем каталоге торрентов."""

from typing import Protocol

from torrcast.domain.release import Release


class TorrentIndex(Protocol):
    """Что сценариям нужно от каталога торрентов - и ничего сверх того."""

    def search(self, query: str, limit: int = 100) -> list[Release]:
        """Раздачи по запросу, не больше ``limit`` штук."""
