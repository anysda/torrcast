"""Строка выдачи, совпадающая с запросом по году и роду; зовёт ожидание кворума круга."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.asked_year import asked_year
from torrcast.domain.find_year import _find_year
from torrcast.domain.normalize import _normalize
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.domain.raw_result import RawResult


def _any(_row: RawResult) -> bool:
    return True


def query_fits(query: str) -> Callable[[RawResult], bool]:
    """Подходит ли строка тому, что назвал сам запрос: год последним словом, сериал серией.

    Год человек берёт из нашего же меню («Призрак в доспехах 2026», TC-777), серию называет
    сам («хорошая жена s1e1»). Не назвал ни того ни другого - подходит любая строка: гадать
    за человека нечего. Год в имени картины («Бегущий по лезвию 2049») читается как год, и
    такая строка не подойдёт: круг тогда просто ждёт кворум, как ждал без строк вовсе.

    Подходит только строка, которой картина года может играть дефолтом: живая
    (:data:`ALIVE_SEEDERS`) и не названный HEVC (:func:`is_candidate` его не берёт). На
    стенде 04.10 RuTor привёз к «Призрак в доспехах 2026» одну строку 2026 года,
    WEBRip-HEVC на 88 сидов: она отпустила Knaben с его WEB-DL 2026, и дефолтом встала
    картина 2006 года (4 из 16 поисков, ветка и dev поровну).
    """
    _name, year = asked_year(query)
    series = parse_release_name(query).kind == "tv"
    if year is None and not series:
        return _any

    def fits(row: RawResult) -> bool:
        # the year the name parse finds, without the rest of the parse: rows of other years are many
        if year is not None and _find_year(_normalize(row.title))[0] != year:
            return False
        if row.seeders < ALIVE_SEEDERS:
            return False
        release = parse_release_name(row.title)
        return not release.is_hevc and (not series or release.kind == "tv")

    return fits


__all__ = ["query_fits"]
