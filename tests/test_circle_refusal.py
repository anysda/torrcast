"""Зеркало разбора отказа круга: немое «ничего не нашлось» и названная причина."""

from __future__ import annotations

import json

from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.circle_refusal import circle_refusal


def _said(failed: TorrcastError) -> tuple[int, dict[str, str]]:
    answer = circle_refusal(failed)
    said: dict[str, str] = json.loads(answer.body)
    return answer.code, said


def test_a_mute_refusal_is_answered_as_a_picture_without_releases() -> None:
    """🔴 TC-1308: строку разбора зритель читал вместо слов продукта.

    Немой отказ круга поиск держит пустым экраном, а не отказом, и карточке сказать нечего
    сверх того же: 404 - тот самый ответ, на котором страница рисует обложку плитки, её
    имя и «раздач нет», а не чужие слова про запрос.
    """
    assert _said(NothingFoundError("ничего не нашлось по “тачки”")) == (404, {"error": "not_found"})


def test_a_named_refusal_keeps_its_own_words_for_the_viewer() -> None:
    """Круг знает, почему раздач нет, и эти слова зритель читает такими же, как в выдаче."""
    assert _said(TorrcastError("раздач с сезоном 9 нет")) == (
        409,
        {"error": "раздач с сезоном 9 нет"},
    )
