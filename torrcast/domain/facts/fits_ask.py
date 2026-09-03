"""Та ли это картина: сверка года и рода найденной статьи; зовёт отбор статей постера."""

from __future__ import annotations

from typing import Final

from torrcast.domain.facts.ask import Ask
from torrcast.domain.facts.dated import Dated

#: Допуск по году, лет. Ноль тут выбран не из строгости: у P577 лежат ВСЕ даты
#: публикации разом (фестиваль, прокат, издания), и совпадение ищется с любой из них, а
#: допуск в год добирал бы уже соседку по имени - «Аниматрица» 2003-го приезжала так под
#: «Возвращение к источнику» 2004-го.
_SLACK: Final = 0


def fits_ask(ask: Ask, row: Dated, known: dict[str, set[int]]) -> bool:
    """Подходит ли статья этой картине; ``known`` - годы, добранные из Wikidata.

    Про род молчание - не отказ: род читается из категорий и есть не у всех статей.
    Про год молчание - отказ, и это главное правило: неподтверждённый год отдавал пяти
    «Паразитам» разных лет одну и ту же картинку 2019 года.
    """
    return _same_kind(ask.kind, row) and _same_year(ask.year, row, known)


def _same_kind(kind: str, row: Dated) -> bool:
    """Тот ли это род: спрошен не фильм и не сериал или статья про род молчит - да.

    Год один и тот же бывает у фильма и у сериала под одним именем: «Паразиты» 2019
    года - это и корейский фильм, и сериал, и без рода в список приезжали две строки с
    ОДНОЙ картинкой.
    """
    return kind not in ("movie", "tv") or not row.kinds or kind in row.kinds


def _same_year(year: int | None, row: Dated, known: dict[str, set[int]]) -> bool:
    """Тот ли это год: год не спрошен - подходит любая статья."""
    if year is None:
        return True
    seen = row.years or known.get(row.entity, set())
    return any(abs(one - year) <= _SLACK for one in seen)
