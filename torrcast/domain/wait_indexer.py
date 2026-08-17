"""Опорные источники: их выдачу круг дожидается, прежде чем показать список."""

from __future__ import annotations

from typing import Final

from torrcast.domain.quorum_indexer import QUORUM_INDEXERS

#: Источники, которым даём доехать в первый пул. RuTor здесь остаётся ради русской
#: озвучки, но кворумом больше не считается: сохранённые 170 кругов дали максимум
#: живого ответа 1.761 с, поэтому три секунды сохраняют все его строки, а смерть
#: отнимает только эти три секунды и честно сужает каталог.
WAIT_INDEXERS: Final = (*QUORUM_INDEXERS, "rutor")


def wait_indexer(name: str) -> bool:
    """Нужен ли источник в первом пуле, даже если без него поиск способен жить."""
    low = name.lower()
    return any(part in low for part in WAIT_INDEXERS)


__all__ = ["WAIT_INDEXERS", "wait_indexer"]
