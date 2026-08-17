"""Первая фраза статьи под потолок меню; зовёт печать меню франшизы."""

from __future__ import annotations

from torrcast.domain.facts.sentence import sentence
from torrcast.domain.facts.settings import BLURB_CAP


def shorten(extract: str, limit: int = BLURB_CAP) -> str:
    """Первая фраза статьи под потолок :data:`BLURB_CAP`; многоточие — только если не влезла.

    Ширина терминала тут ни при чём: фраза переносится по словам (:func:`~torrcast.cli.
    menu_lines`) и занимает столько строк, сколько ей нужно. Обрыв многоточием остаётся
    ровно для того случая, ради которого он и заводился — фраза длиннее всякого разумного.
    """
    first = sentence(extract)
    if len(first) <= limit:
        return first
    cut = first[:limit].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return f"{cut}..." if cut else ""
