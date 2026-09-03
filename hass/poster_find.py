"""Постер картины по её просьбам: один поход в сеть, без полки и без запасного кадра.

Зовут отсюда двое, и правило у них обязано быть одно: картинка играющей картины
(:class:`hass.posters.Posters`) и картинки найденных картин в списке обзора
(:class:`hass.hit_posters.HitPosters`). Разъехавшись, они принесли бы под одним именем
разные картинки - и человек увидел бы в списке не то, что потом заиграет.

🔴 Сеть тут не глотается в тишину, а переводится в «постера нет»: у зовущего есть свой
ответ на пустоту (кадр показа у карточки, голая строка у списка), и различать 429,
обрыв и картину без английской статьи ему нечем. Настоящий отказ виден отложенной
следующей попыткой, а не молчанием.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from torrcast.domain.facts.ask import Ask

Poster = Callable[[Ask, float], bytes | None]


def poster_find(asks: Sequence[Ask], timeout: float, poster: Poster) -> bytes | None:
    """Байты постера по записанным именам картины; не нашлось - ``None``.

    Имена перебираются в порядке доверия, а год и род едут с каждым: ими справка
    отличает картину от тёзки (:class:`~torrcast.adapters.wiki.poster_pages.PosterPages`),
    и без них в список приехал бы постер соседней картины.
    """
    for ask in asks:
        try:
            body = poster(ask, timeout)
        except Exception:
            continue
        if body:
            return body
    return None
