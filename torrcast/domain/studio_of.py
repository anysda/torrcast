"""Опознаёт студию по заголовку дорожки."""

import re
from typing import Final

from torrcast.domain.studio import STUDIOS, Studio

#: Всё, что не буква и не цифра, - разделитель слов: «[TVShows][MVO]», «AVO-Сербин»,
#: «Дубляж. (MovieDalen)» подписаны одной и той же студией, а разделены по-разному.
_WORDS_RE: Final = re.compile("[^0-9a-zа-яё]+", re.IGNORECASE)


def studio_of(title: str | None) -> Studio | None:
    """Студия из заголовка дорожки по :data:`STUDIOS`; ``None`` — незнакомая или её нет.

    Сравниваем по словам, а не подстрокой: иначе «Ancord» нашёлся бы в любом слове,
    которое его содержит. Из нескольких совпадений берём самое длинное имя - «HDRezka
    Studio» точнее, чем «HDRezka», и если однажды они разъедутся по ступеням, победит
    более подробная запись.
    """
    words = f" {_WORDS_RE.sub(' ', (title or '').casefold()).strip()} "
    hit = [key for key in STUDIOS if f" {key} " in words]
    return STUDIOS[max(hit, key=len)] if hit else None
