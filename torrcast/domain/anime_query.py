"""Признак «запрос похож на аниме»: по нему анимешные индексеры идут в первый круг."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.looks_anime import looks_anime

#: Кино-маркеры в латинском запросе: год или явное «фильм/сериал/сезон». Такой запрос
#: анимешным не бывает, и Nyaa на нём - лишний участник круга.
NOT_ANIME_RE: Final = re.compile(
    r"\b(?:19|20)\d{2}\b|\bmovies?\b|\bfilms?\b|\bseries\b|\bseason\b|\bs\d{1,2}\b",
    re.IGNORECASE,
)
#: Кириллица в запросе: каталог Nyaa ромадзи/английский, и русскоязычный запрос без
#: аниме-слов он молчит почти всегда.
CYRILLIC_RE: Final = re.compile(r"[а-яё]", re.IGNORECASE)


def anime_query(query: str) -> bool:
    """Запрос похож на аниме - значит Nyaa и прочие анимешные индексеры идут в основном
    круге, а не фолбэком (TC-229).

    Признак нарочно дешёвый, две проверки. Прямые слова - «аниме», японские жанры,
    OVA, ``[TV]`` (тот же узкий список, что судит имена раздач,
    :func:`~torrcast.domain.looks_anime.looks_anime`). Иначе - латиница без кино-маркеров
    (:data:`NOT_ANIME_RE`): каталог Nyaa ромадзи/английский, и оригинальное имя аниме
    («Frieren», «Steins Gate») неотличимо от имени картины, поэтому сомнение трактуем
    в пользу вызова - полноту аниме ронять нельзя. Зато русскоязычный запрос без
    аниме-слов Nyaa молчит почти всегда (замер 09-08-2026: пусто в 79% запросов,
    строки - только на аниме), и там он зовётся лишь фолбэком на тощем пуле -
    параллель по нему лимитирована, и лишний круг это лишний риск 504-бана Prowlarr
    на часы.
    """
    if looks_anime(query):
        return True
    if CYRILLIC_RE.search(query):
        return False
    return not NOT_ANIME_RE.search(query)


__all__ = ["CYRILLIC_RE", "NOT_ANIME_RE", "anime_query"]
