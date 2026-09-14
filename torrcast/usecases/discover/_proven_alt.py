"""Ручается ли имя добора само за себя: оно от справки или это слова самого запроса."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.romaji import romaji
from torrcast.domain.transliterate import transliterate


def _proven_alt(alt: str, name: str, about: Origin) -> bool:
    """Имя добора от справки, её русское имя, транслит или романизация запроса.

    Транслит и романизация - те же слова запроса другой записью: чужой картины они
    принести не могут. Оригинал из справки отвечает про ту самую картину. А вот оригинал,
    вычитанный у раздачи выдачи, ничем не подтверждён и за себя не ручается.
    """
    return (
        bool(about.title) or alt == about.name or alt == transliterate(name) or alt == romaji(name)
    )


__all__ = ["_proven_alt"]
