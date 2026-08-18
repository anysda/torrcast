"""Извлекает номер сезона и серии из пользовательского текста."""

import re
from typing import Final

from torrcast.domain.episode import Episode

__all__ = ["parse_episode"]

_MERGED_TAIL: Final = r"(?:[_exх]\d{1,3})?"
_PATTERNS: Final = (
    re.compile(
        r"\bs\s*(?P<season>\d{1,2})\s*[.\-_ ]?\s*e\s*(?P<episode>\d{1,3})" + _MERGED_TAIL + r"\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?P<season>\d{1,2})\s*[xх]\s*(?P<episode>\d{1,3})" + _MERGED_TAIL + r"\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?P<season>\d{1,2})\s*сезон\D{0,14}?(?P<episode>\d{1,3})\s*сери\w*", re.I),
    re.compile(r"(?P<episode>\d{1,3})\s*сери\D{0,14}?(?P<season>\d{1,2})\s*сезон\w*", re.I),
)


def parse_episode(text: str) -> Episode | None:
    """Вытащить ``sNeM`` из распространённых русских и scene-форматов."""
    for pattern in _PATTERNS:
        match = pattern.search(text)
        if match:
            return Episode(int(match.group("season")), int(match.group("episode")))
    return None
