"""Кворум индексеров: без кого пустая выдача не доказывает, что фильма нет."""

from __future__ import annotations

from typing import Final

#: 🔴 Кворум - источник, без которого пустая выдача не доказывает, что фильма нет.
#: Knaben несёт 41% строк и весь западный хвост. RuTor прежде нёс 56%, но после TC-488
#: у русской озвучки есть сменный источник, поэтому его бан сужает каталог, а не убивает поиск.
QUORUM_INDEXERS: Final = ("knaben",)


def quorum_indexer(name: str) -> bool:
    """Индексер из кворума (:data:`QUORUM_INDEXERS`) - тот, без которого выдачи нет.

    Имя приходит от Prowlarr как есть («Knaben», «RuTor»), поэтому сверяем подстрокой
    в нижнем регистре - ровно как :func:`~torrcast.domain.anime_indexer.anime_indexer`.
    """
    low = name.lower()
    return any(part in low for part in QUORUM_INDEXERS)


__all__ = ["QUORUM_INDEXERS", "quorum_indexer"]
