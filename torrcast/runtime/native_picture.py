"""Происхождение картины как доказательство языка безымянной дорожки."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.same_name import same_name
from torrcast.domain.picture import Picture
from torrcast.runtime.facts_wiring import FACTS


def native_picture(picture: Picture, query: str, known: Origin | None = None) -> None:
    """Перенести уже полученный паспорт происхождения в картину перед отбором звука.

    Пустой оригинал при известном русском имени означает отечественную картину. Паспорт
    спрашивает поиск, но первый успешный круг не проходит через добор, где раньше только
    и ставился :attr:`Picture.native`. Здесь сеть не спрашивается: читается тот же уже
    сохранённый ответ, а если он молчит или ещё не успел - поведение остаётся прежним.
    """
    about = known
    if about is None:
        series = picture.kind == "tv"
        about = FACTS.cache.read(query, series) or FACTS.cache.read(query, None)
    if about and about.name and not about.title and same_name(picture.title, about.name):
        picture.native = True
