"""Зеркало разбора отказа круга: немое «ничего не нашлось» и названная причина."""

from __future__ import annotations

import json

from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.torrcast_error import TorrcastError
from web.circle_refusal import circle_refusal


def _said(failed: TorrcastError | None, whole: bool = False) -> tuple[int, dict[str, object]]:
    answer = circle_refusal(failed, whole)
    said: dict[str, object] = json.loads(answer.body)
    return answer.code, said


def test_a_mute_refusal_is_answered_as_a_picture_without_releases() -> None:
    """🔴 TC-1308: строку разбора зритель читал вместо слов продукта.

    Немой отказ круга поиск держит пустым экраном, а не отказом, и карточке сказать нечего
    сверх того же: 404 - тот самый ответ, на котором страница рисует обложку плитки, её
    имя и «раздач нет», а не чужие слова про запрос.
    """
    assert _said(NothingFoundError("ничего не нашлось по “тачки”")) == (
        404,
        {"error": "not_found", "whole": False},
    )


def test_a_named_refusal_never_carries_the_process_language_to_the_viewer() -> None:
    """Веб узнаёт только код: фразу берёт его английский каталог."""
    assert _said(TorrcastError("раздач с сезоном 9 нет")) == (
        409,
        {"error": "search_refused", "whole": False},
    )


def test_only_a_whole_catalogue_may_say_nothing_can_be_found() -> None:
    """«Играть» гаснет только на пустоте, которую подтвердил каждый индексер."""
    assert _said(NothingFoundError("пусто"), whole=True)[1]["whole"] is True
    assert _said(NotFoundError("раздач с сезоном 9 нет"), whole=True)[1]["whole"] is True
    assert _said(None, whole=True) == (404, {"error": "not_found", "whole": True})


def test_a_broken_circle_is_never_whole() -> None:
    """Сорванный круг ничего не доказал, даже если его клиенты успели ответить."""
    assert _said(InfraError("индексеры недоступны"), whole=True)[1]["whole"] is False
