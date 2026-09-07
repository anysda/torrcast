"""Все имена, которыми зовут одну картину; используют отбор по имени и карточка."""

from __future__ import annotations

from torrcast.domain.picture import Picture


def picture_names(picture: Picture) -> set[str]:
    """Имена картины: своё, оригинальное, второе имя склейки и алиасы раздач.

    У одной картины имён столько, сколько её называли: лента раздач знает «Better Days»,
    каталог зовёт её «Лучшие дни», а оригинал у неё «Shao nian de ni». Сверять человека
    или ключ с ОДНИМ из них - значит не узнать картину по двум остальным.

    Алиасы приезжают уже слагами (:func:`torrcast.domain.alias_slugs._alias_slugs`), и
    приводить их не надо: слаг слага - он сам. Пустых имён в наборе нет: пустое имя не
    называет ничего, а в сверке оно совпало бы со всякой картиной без оригинала.
    """
    named = {picture.title, picture.original or "", picture.also or "", *picture.aliases}
    return {name for name in named if name}


__all__ = ["picture_names"]
