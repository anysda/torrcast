"""Опознаёт студию по заголовку дорожки."""

from torrcast.domain.studio import Studio
from torrcast.domain.studios_in import studios_in


def studio_of(title: str | None) -> Studio | None:
    """Студия из заголовка дорожки по :data:`STUDIOS`; ``None`` — незнакомая или её нет.

    Из нескольких совпадений берём самое длинное имя - «HDRezka Studio» точнее, чем
    «HDRezka», и если однажды они разъедутся по ступеням, победит более подробная
    запись. Заголовок дорожки называет ОДНУ студию, поэтому ответ тут один; имя раздачи
    перечисляет их пачкой, и его разбирает :func:`studios_in`.
    """
    hit = studios_in(title)
    return max(hit, key=lambda studio: len(studio.name)) if hit else None
