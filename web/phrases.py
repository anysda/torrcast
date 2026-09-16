"""Словарь надписей страницы: ``GET /api/phrases``."""

from __future__ import annotations

import json

from torrcast.domain.catalogs.tongue import EN, RU, tongue
from torrcast.domain.catalogs.web.en import en as english
from torrcast.domain.catalogs.web.ru import ru as russian
from web.answer import Answer
from web.request import Request


def phrases(request: Request) -> Answer:
    """Отдать надписи страницы; без ``?lang=`` - на языке самого экземпляра.

    Спросить :func:`torrcast.domain.catalogs.phrase.phrase` тут нечем: он отвечает ОДНОЙ
    надписью, а странице нужен весь словарь. А вот ЯЗЫК берётся у того же держателя, что
    и у него (:func:`torrcast.domain.catalogs.tongue.tongue`): экземпляр с
    ``language: ru`` в настройке говорил по-русски всюду, кроме собственной страницы, -
    она одна не спрашивала язык и получала английский словарь (TC-1305). Набор ключей у
    обоих языков один и тот же - это сторожит зеркало каталога, а не эта функция.

    Язык ответа назван заголовком: страница считает по нему числительные и даты, и
    догадываться о нём по своему же вопросу ей нельзя - вопроса могло и не быть.
    """
    asked = request.query.get("lang") or tongue()
    said = RU if asked == RU else EN
    spoken = russian() if said == RU else english()
    return Answer(
        200,
        json.dumps(spoken, ensure_ascii=False).encode("utf-8"),
        extra=(("Content-Language", said),),
    )
