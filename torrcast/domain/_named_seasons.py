"""Читает явно названные сезоны и названную серию из имени раздачи."""

from __future__ import annotations

import re
from itertools import pairwise
from typing import Final

# Шаблоны сезонов перенесены из PTT (Python-порт parse-torrent-title):
# https://github.com/dreulavelle/PTT, PTT/handlers.py,
# коммит 88429bb90acef55673f421f45038878809b1e577.
# Переведены с `regex` на `re`; порядок и грамматика границ сохранены. Отличия: русские падежи
# слова «сезон», русский диапазон перед словом, запрет цифры сразу за номером и отказ читать
# сезонами номера серий («Сезон: 9 / 10 серий», «5 сезон: 1-3 серии»). Без «series N» и
# «Seasons ... N-M» через всё имя: оба ловят серии и годы. Строки тестов PTT лежат в
# tests/domain/test__named_seasons.py.
#
# MIT License
#
# Copyright (c) 2024 Spoked
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

_I: Final = re.IGNORECASE
_LEAD: Final = r"(?:complete\W|seasons?\W|\W|^)"
_COMPLETE: Final = r"(?:(?:\bthe\W)?\bcomplete\W)?"
_WORD: Final = r"(?:seasons?|сезон(?:ы|а|ов|и)?)"
#: Номер сезона не стоит перед словом «сезон»: «5 сезон: 1-3» - серии пятого.
_NOT_AFTER_NUMBER: Final = r"(?<!\d)(?<!\d\s)"
#: Перечень, за которым идёт слово «серии», - это серии, а не сезоны.
_NOT_EPISODES: Final = r"(?![.,]\d)(?!\s*(?:сери|эпизод|episodes?\b))"

_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(_LEAD + r"((?:s\d{1,2}[., +/\\&-]+)+s\d{1,2}\b)", _I),
    re.compile(_LEAD + r"[([]?(s\d{2,}-\d{2,}\b)[)\]]?", _I),
    re.compile(_LEAD + r"[([]?(s[1-9]-[2-9])(?!\d)[)\]]?", _I),
    re.compile(
        _NOT_AFTER_NUMBER
        + _COMPLETE
        + _WORD
        + r"[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[., /\\&]+)+\d{1,2}\b)"
        + _NOT_EPISODES,
        _I,
    ),
    re.compile(
        _NOT_AFTER_NUMBER
        + _COMPLETE
        + _WORD
        + r"[. ]?[-:]?[. ]?[([]?((?:\d{1,2}[.-]+)+[1-9]\d?\b)"
        + _NOT_EPISODES,
        _I,
    ),
    re.compile(
        _COMPLETE + r"season[. ]?[([]?((?:\d{1,2}[. -]+)+[1-9]\d?\b)(?![.,]\d)(?!.*\.\w{2,4}$)", _I
    ),
    re.compile(
        _COMPLETE + r"\bseasons?\b[. -]?(\d{1,2}[. -]?(?:to|thru|and|\+)[. -]?\d{1,2})\b", _I
    ),
    re.compile(_COMPLETE + r"(?:saison|seizoen|season|temporada):?[. ]?(\d{1,2})\b", _I),
    re.compile(r"(?<!\d)(\d{1,2}\s*-\s*\d{1,2})(?:-?й)?[. _]?сезон", _I),
    re.compile(r"(?<!\d)(\d{1,2})(?:-?й)?[. _]?(?:сезон|sez(?:on)?)(?:\W?\D|$)", _I),
    re.compile(r"сезон:?[. _]?№?(\d{1,2})(?!\d)", _I),
    re.compile(r"(?:\W|^)(\d{1,2})[. ]?(?:st|nd|rd|th)[. ]*season", _I),
)
#: Одна названная серия («Серия: 5», «Эпизод 21», «Серия №180»), не перечень «Серии: 1-10».
_NAMED_EPISODE: Final = re.compile(
    r"(?:эпизод|серия)[. ]?[-:#№]?[. ]?(\d{1,4})(?!\d)(?!\s*(?:-|из|of)\s*\d)", _I
)
#: Сезон с номером больше этого - год или серия, а не сезон.
_MOST: Final = 40


def _named_seasons(text: str) -> tuple[int, ...]:
    """Вернуть все сезоны, прямо названные первой сработавшей сезонной пометкой."""
    for pattern in _PATTERNS:
        match = pattern.search(text)
        if match and (numbers := _range(match.group(1))):
            return numbers
    return ()


def _named_episode(text: str) -> int | None:
    """Номер одной названной словом серии или ``None``."""
    match = _NAMED_EPISODE.search(text)
    return int(match.group(1)) if match else None


def _range(values: str) -> tuple[int, ...]:
    """Перенос ``range_func`` из PTT: два числа - диапазон, больше - только подряд.

    Перечень через запятую («Сезон: 1, 3», его же пишет адаптер JacRed) PTT растягивал
    в диапазон 1-3; тут он остаётся перечнем, если идёт по возрастанию.
    """
    numbers = [int(number) for number in re.findall(r"\d+", values)]
    if not numbers or not all(0 < number <= _MOST for number in numbers):
        return ()
    if not re.search(r"-|to|thru", values, _I):
        return tuple(numbers) if numbers == sorted(set(numbers)) else ()
    if len(numbers) == 2 and numbers[0] < numbers[1]:
        return tuple(range(numbers[0], numbers[1] + 1))
    if len(numbers) > 2 and all(b == a + 1 for a, b in pairwise(numbers)):
        return tuple(numbers)
    return (numbers[0],) if len(numbers) == 1 else ()


__all__ = ["_named_episode", "_named_seasons"]
