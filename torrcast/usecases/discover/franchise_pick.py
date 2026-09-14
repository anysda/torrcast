"""Картины франшизы по имени запроса, где спор тёзок решает и офлайн-карта IMDb."""

from __future__ import annotations

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture


def franchise_pick(
    query: str, pictures: list[Picture], *, join_continuations: bool = True
) -> list[Picture]:
    """:func:`pick_franchise` с картой, поставленной проводкой: один ответ на всех путях.

    Разбор зовут первый круг, паспортная сверка и оба добора, и каждый переспрашивает имя
    заново на своей выдаче. Карта у них обязана быть одна: без неё добор по голосу снова
    отдавал «Мы» (2019) соседу по слову, которого первый круг только что отверг.
    """
    return pick_franchise(
        query, pictures, join_continuations=join_continuations, imdb=_search_state._search_known
    )
