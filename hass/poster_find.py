"""Постер картины по её именам: один поход в сеть, без полки и без запасного кадра.

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

from collections.abc import Callable

Poster = Callable[[str, int | None, str, float], bytes | None]
Correct = Callable[[str, int, str, float], str]


def poster_find(
    names: list[str],
    year: int | None,
    kind: str,
    timeout: float,
    poster: Poster,
    correct: Correct | None,
) -> bytes | None:
    """Байты постера по записанным именам картины; не нашлось - ``None``.

    Имена перебираются в порядке доверия, а год и род едут с каждым: ими справка
    отличает картину от тёзки (:func:`torrcast.domain.facts.titles_for.titles_for`), и
    без них в список приехал бы постер соседней картины.

    Последняя попытка - имя, исправленное самой Википедией, и берётся оно только когда
    паспорт подтвердил тот же год и тот же род (:func:`hass.poster_lookup._wiki_correction`).
    """
    for name in names:
        try:
            body = poster(name, year, kind, timeout)
        except Exception:
            continue
        if body:
            return body
    if not (names and year and correct is not None):
        return None
    try:
        fixed = correct(names[0], year, kind, timeout)
        if fixed and fixed not in names:
            return poster(fixed, year, kind, timeout)
    except Exception:
        return None
    return None
