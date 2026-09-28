"""Отказ круга поиска, прочитанный карточкой: немой отдельно от названного."""

from __future__ import annotations

import json

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.answer import Answer


def circle_refusal(failed: TorrcastError | None, whole: bool) -> Answer:
    """Круг не дал раздач: молчание отвечается иначе, чем названная причина.

    «Ничего не нашлось» - это ОТВЕТ круга, а не сорванный круг, и поиск держит его ровно
    так (:meth:`hass.search_job.SearchJob.run`): пустой список, пустой экран, ни слова
    отказа. Карточка же валила его в общий род отказов и выкладывала зрителю строку
    разбора («ничего не нашлось по “...”») вместо своих слов (TC-1308). Ответ тот же, что
    и у картины, которой в круге не оказалось (``failed`` пуст): её обложка, её имя и
    «раздач нет».

    Названный отказ - другое дело: круг ЗНАЕТ, почему раздач нет («раздач с сезоном 9
    нет», «во франшизе столько частей нет», «не настроен Prowlarr»), и эти слова зритель
    читает на карточке теми же, какими прочёл бы в выдаче.

    ``whole`` - ответил ли каталог целиком (:class:`web.heard_circle.HeardCircle`). Без него
    «Играть» не гаснет: пустота урезанного каталога - не «найти невозможно», а повод
    поискать на клике. Сорванный круг (не :class:`NotFoundError`) целым не бывает никогда.
    """
    whole = whole and (failed is None or isinstance(failed, NotFoundError))
    if failed is None or isinstance(failed, NothingFoundError):
        return _said(404, "not_found", whole)
    return _said(409, str(failed), whole)


def _said(code: int, word: str, whole: bool) -> Answer:
    body = {"error": word, "whole": whole}
    return Answer(code, json.dumps(body).encode("utf-8"))
