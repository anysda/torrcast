"""Словарь надписей страницы: ``GET /api/phrases``."""

from __future__ import annotations

import json

from torrcast.domain.catalogs.tongue import RU
from torrcast.domain.catalogs.web.en import en as english
from torrcast.domain.catalogs.web.ru import ru as russian
from web.answer import Answer
from web.request import Request


def phrases(request: Request) -> Answer:
    """Отдать надписи страницы на языке из ``?lang=``; умолчание - английский.

    Спросить :func:`torrcast.domain.catalogs.phrase.phrase` тут нечем: он отвечает ОДНОЙ
    надписью и берёт язык у процесса (:func:`torrcast.domain.catalogs.tongue.tongue`), а
    странице нужен весь словарь и язык из запроса. Набор ключей у обоих языков один и тот
    же - это сторожит зеркало каталога, а не эта функция.
    """
    spoken = russian() if request.query.get("lang") == RU else english()
    return Answer(200, json.dumps(spoken, ensure_ascii=False).encode("utf-8"))
