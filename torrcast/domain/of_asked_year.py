"""Картины года, названного запросом; зовут меню, франшиза и взятие тёзки."""

from __future__ import annotations

from torrcast.domain.asked_year import asked_year
from torrcast.domain.picture import Picture


def of_asked_year(pictures: list[Picture], query: str) -> list[Picture]:
    """Картины года, названного последним словом запроса; год не назван - пусто.

    🔴 TC-1398. Год в конце собственного имени картины - это имя, а не год: строка
    «Бегуший по лезвию 2049» склеилась в картину 2049 года, и на «Бегущий по лезвию 2049»
    она вставала бы картиной названного года.
    """
    year = asked_year(query)[1] if query else None
    if year is None:
        return []
    return [p for p in pictures if p.year == year and not p.title.rstrip().endswith(str(year))]


__all__ = ["of_asked_year"]
