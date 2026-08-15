"""Происхождение картины как доказательство языка безымянной дорожки."""

from __future__ import annotations

from torrcast.facts import Origin, _cached_origin, same_name
from torrcast.parse import Picture


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
        about = _cached_origin(query, series) or _cached_origin(query, None)
    if about and about.name and not about.title and same_name(picture.title, about.name):
        picture.native = True
