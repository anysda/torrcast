"""Байты пачки постеров частями: доехавшая картинка ложится сразу, а не с последней в пачке.

Пачка качалась одним шагом (:meth:`~hass.poster_source.PosterSource.bodies`), и ни одна её
картинка не ложилась, пока не вернулась самая медленная. На стенде в минуту 429 выдача
«Начало» держала 18 скачанных обложек из 27 невидимыми до конца прогона: одна картинка
ждала тишину, а страница показывала две. Картины с одними и теми же адресами идут одной
частью: общий постер сборника и его первой части по-прежнему качается один раз.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Final

from torrcast.domain.facts.ask import Ask

#: Сколько частей качается разом; сами файлы Wikimedia всё равно идут по две
#: (:data:`~torrcast.adapters.wiki.http_json_client.IMAGE_LANES`).
_PARTS: Final = 4


def poster_parts(
    wanted: dict[Ask, list[str]], land: Callable[[dict[Ask, list[str]]], None]
) -> None:
    """Отдать ``land`` пачку частями по адресам и дождаться, пока лягут все."""
    parts: dict[tuple[str, ...], dict[Ask, list[str]]] = {}
    for ask, addresses in wanted.items():
        parts.setdefault(tuple(addresses), {})[ask] = addresses
    with ThreadPoolExecutor(max_workers=_PARTS, thread_name_prefix="poster-part") as lanes:
        list(lanes.map(land, parts.values()))


__all__ = ["poster_parts"]
