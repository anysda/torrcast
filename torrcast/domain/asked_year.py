"""Год, названный отдельным словом в конце запроса; зовёт отбор картин франшизы."""

from __future__ import annotations

import re
from typing import Final

_ASKED_YEAR: Final = re.compile(r"^(?P<name>.+?)[\s,]+(?P<year>(?:19|20)\d{2})$")


def asked_year(query: str) -> tuple[str, int | None]:
    """Имя запроса и год, названный последним словом: «Байки Мэтра 2008» → 2008.

    🔴 TC-777. Год человек берёт из напечатанного нами же меню - «(2008, сериал)», - и
    отказывать по нему нельзя. Отдельным словом: «2049» в «Бегущем по лезвию 2049» это
    часть имени, а не год, и трогать его нечем - в конце там стоит само название.
    Отличить одно от другого мы и не беремся: год отрезается ТОЛЬКО как последняя
    попытка, когда по всему запросу целиком не нашлось ничего.
    """
    match = _ASKED_YEAR.match(query.strip())
    if not match:
        return (query.strip(), None)
    return (match.group("name").strip(), int(match.group("year")))


__all__ = ["asked_year"]
