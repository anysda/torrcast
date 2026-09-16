"""Отказ круга поиска, прочитанный карточкой: немой отдельно от названного."""

from __future__ import annotations

from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.answer import Answer
from web.refusal import refusal


def circle_refusal(failed: TorrcastError) -> Answer:
    """Круг не дал раздач: молчание отвечается иначе, чем названная причина.

    «Ничего не нашлось» - это ОТВЕТ круга, а не сорванный круг, и поиск держит его ровно
    так (:meth:`hass.search_job.SearchJob.run`): пустой список, пустой экран, ни слова
    отказа. Карточка же валила его в общий род отказов и выкладывала зрителю строку
    разбора («ничего не нашлось по “...”») вместо своих слов (TC-1308). Ответ тот же, что
    и у картины, которой в круге не оказалось: её обложка, её имя и «раздач нет».

    Названный отказ - другое дело: круг ЗНАЕТ, почему раздач нет («раздач с сезоном 9
    нет», «во франшизе столько частей нет», «не настроен Prowlarr»), и эти слова зритель
    читает на карточке теми же, какими прочёл бы в выдаче.
    """
    if isinstance(failed, NothingFoundError):
        return refusal(404, "not_found")
    return refusal(409, str(failed))
