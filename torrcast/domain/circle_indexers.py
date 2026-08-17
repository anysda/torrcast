"""Кого из индексеров зовём первым кругом, а кого оставляем фолбэку."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TypeAlias

from torrcast.domain.anime_indexer import anime_indexer
from torrcast.domain.anime_query import anime_query

#: Индексер, каким его назвал Prowlarr: номер и имя.
Indexer: TypeAlias = tuple[int, str]


def circle_indexers(
    pairs: Sequence[Indexer], query: str
) -> tuple[tuple[Indexer, ...], tuple[Indexer, ...]]:
    """Разложить индексеров на первый круг и на фолбэк (TC-229).

    🔴 Анимешные индексеры (Nyaa и прочие,
    :func:`~torrcast.domain.anime_indexer.anime_indexer`) - не всегда в круге. Nyaa молчит
    на явно не-аниме запросах (замер 09-08-2026: пусто в 79% запросов), а параллель по
    нему лимитирована - 2-4 одновременных, дальше 504 и health-бан Prowlarr на часы.
    Поэтому на не-аниме запросе (:func:`~torrcast.domain.anime_query.anime_query`) первый
    круг идёт без него, и лишь если пул вышел тощим, анимешные зовутся вторым кругом.

    Фолбэк пуст, когда откладывать нечего или незачем: без анимешных круг был бы пуст,
    анимешных нет вовсе, или запрос похож на аниме. Тогда первым кругом идут все.
    """
    anime = tuple(pair for pair in pairs if anime_indexer(pair[1]))
    main = tuple(pair for pair in pairs if not anime_indexer(pair[1]))
    if not main or not anime or anime_query(query):
        return tuple(pairs), ()
    return main, anime


__all__ = ["Indexer", "circle_indexers"]
