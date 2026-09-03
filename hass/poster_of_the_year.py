"""Постер картины ИМЕННО ЭТОГО года; зовёт список находок обзора."""

from __future__ import annotations

from hass.poster_find import Correct, Poster, poster_find


def poster_of_the_year(
    title: str,
    year: int | None,
    kind: str,
    timeout: float,
    poster: Poster,
    correct: Correct | None,
) -> bytes | None:
    """Постер картины ИМЕННО ЭТОГО года; год не подтверждён - картинки нет.

    🔴 Голое название ведёт в одну статью на всех тёзок: «Паразиты» 1999, 2004, 2016 и
    2019 годов приводят к одному и тому же постеру, а «Джентльмены» 2019 года - к постеру,
    под которым в списке стоит сериал 2024-го. Поэтому имя сперва прогоняется через
    паспорт (:func:`hass.poster_lookup._wiki_correction`), и берётся только то, у которого
    справка называет ТОТ ЖЕ год и ТОТ ЖЕ род. Не подтвердила - строка остаётся строкой:
    постер соседней картины хуже, чем никакого.

    Года у картины может не быть вовсе: тогда сверять нечего и нечему противоречить -
    имя идёт как есть.
    """
    if not (year and correct is not None):
        return poster_find([title], year, kind, timeout, poster, None)
    try:
        fixed = correct(title, year, kind, timeout)
    except Exception:
        return None
    if not fixed:
        return None
    return poster_find([fixed], year, kind, timeout, poster, None)
