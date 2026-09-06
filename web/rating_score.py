"""Оценка числом из строки справки: ``«IMDb 8.7» -> 8.7``."""

from __future__ import annotations

import re
from typing import Final

#: Первое число в строке: «IMDb 8.7», «Рейтинг IMDb 7,6» - оценка; «IMDb» - её нет.
_SCORE: Final = re.compile(r"\d+(?:[.,]\d+)?")


def rating_score(rating: str) -> float | None:
    """Число из строки рейтинга; нет цифр - нет оценки.

    :class:`torrcast.domain.facts.fact.Fact` держит рейтинг строкой уже с источником
    («IMDb 8.7»): голая цифра в меню телевизора не значила бы ничего. Странице же
    источник дописывает каталог (``web.detail.rating``), и отдать ей ту же строку целиком
    значит показать человеку «IMDb IMDb 8.7». Наружу поэтому едет число, а слово - из
    каталога, как и всякий другой текст человеку.
    """
    found = _SCORE.search(rating)
    return float(found.group().replace(",", ".")) if found else None


__all__ = ["rating_score"]
