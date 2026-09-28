"""Отказ круга поиска, прочитанный карточкой: немой отдельно от названного."""

from __future__ import annotations

import json

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.reason_of import reason_of
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

    Названный отказ не пересылает строку каталога процесса в браузер: на русском
    экземпляре она была бы русской среди слов страницы. Она получает ключ и значения,
    чтобы английский каталог нарисовал именно названную причину.

    ``whole`` - ответил ли каталог целиком (:class:`web.heard_circle.HeardCircle`). Без него
    «Играть» не гаснет: пустота урезанного каталога - не «найти невозможно», а повод
    поискать на клике. Сорванный круг (не :class:`NotFoundError`) целым не бывает никогда.
    """
    whole = whole and (failed is None or isinstance(failed, NotFoundError))
    if failed is None or isinstance(failed, NothingFoundError):
        return _said(404, {"error": "not_found", "whole": whole})
    return _said(
        409, {"error": "search_refused", "reason": reason_of(failed).json(), "whole": whole}
    )


def _said(code: int, body: dict[str, object]) -> Answer:
    return Answer(code, json.dumps(body).encode("utf-8"))
