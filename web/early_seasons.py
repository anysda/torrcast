"""Серии сериала в раннем ответе карточки (:mod:`web.preview`), пока круг раздач идёт.

Список серий ждал весь круг раздач (9-21 с холодно), хотя строки его даёт каталог
(:mod:`web.series_catalog`), а раздачи нужны ему только для того, чтобы решить, чья
нумерация на экране. Первый ответивший индексер уже называет раздачи картины
(:func:`web.early_picture.early_picture`), и каталог решает по ним то же, что решит по
итогу круга: строки те же, что у полной карточки (:func:`web.card_seasons.card_seasons`),
тем же правилом сезонов. Вне каталога здесь пусто: таблицу серий даёт только разбор
раздачи, которую выберет полный круг, а до него неизвестно, какая это раздача.

Сериал из истории не ждёт и первого индексера: его раздача - раздача закладки, и полная
карточка играет его строки ею же (:func:`web.card_seasons._release_for`, закладка главнее).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import replace
from typing import Final, Protocol

from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from web.card_seasons import _bookmark_release, _joined_seasons, _named_seasons, _picture_releases
from web.seasons_from_entry import seasons_from_entry
from web.series_catalog import SERIES

#: Как часто переспрашивать каталог, пока TVmaze в пути: долгий заход оглядывается
#: двадцать раз в секунду, а новое тут приносит только новый ответ индексера.
AGAIN: Final = 1.0
_lock = threading.Lock()
_seen: dict[tuple[str, int, int], tuple[tuple[list[JsonValue], list[int]], bool, float]] = {}
_clock: Callable[[], float] = time.monotonic
_Rows = dict[int, list[JsonValue]]


class _Catalog(Protocol):
    def rows(
        self, picture: Picture, releases: Sequence[Release], saved: _Rows, cold: float
    ) -> tuple[_Rows, bool, list[int]]: ...


def early_seasons(
    picture: Picture | None,
    entry: Entry | None,
    own: Picture | None = None,
    catalog: _Catalog = SERIES,
) -> tuple[list[JsonValue], list[int]]:
    """Вкладки с сериями и числа серий списка по раннему пулу; не из чего - пусто.

    ``own`` - открытая картина: пока пул пуст, её строки даёт раздача закладки.
    """
    if (picture is None or not picture.releases) and own is not None and entry and entry.magnet:
        picture = replace(own, releases=[_bookmark_release(entry)]) if entry.episodes else picture
    if picture is None or picture.kind != "tv" or not picture.releases:
        return [], []
    saved = seasons_from_entry(entry) if entry is not None and entry.episodes else {}
    mark = (picture.key, len(picture.releases), len(entry.episodes) if saved and entry else 0)
    now = _clock()
    with _lock:
        seen = _seen.get(mark)
    if seen is not None and (not seen[1] or now - seen[2] < AGAIN):
        return seen[0]
    releases = _picture_releases(picture)
    known, pending, layout = catalog.rows(picture, releases, saved, 0.0)
    answer: tuple[list[JsonValue], list[int]] = ([], [])
    if known:
        named = {number for release in releases for number in _named_seasons(release)}
        numbers = set(known) if layout else named | set(known) | set(saved)
        answer = _joined_seasons(numbers, known), layout
    with _lock:
        if len(_seen) > 64:  # a screenful of cards, not a history
            _seen.clear()
        _seen[mark] = answer, pending, now
    return answer


__all__ = ["early_seasons"]
