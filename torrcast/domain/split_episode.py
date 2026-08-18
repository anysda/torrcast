"""Отделяет указание серии от пользовательского поискового запроса."""

import re

from torrcast.domain.episode import Episode
from torrcast.domain.parse_episode import _PATTERNS

__all__ = ["split_episode"]


def split_episode(text: str) -> tuple[str, Episode | None]:
    """Вернуть очищенное название и найденный номер сезона/серии."""
    for pattern in _PATTERNS:
        match = pattern.search(text)
        if match:
            rest = f"{text[: match.start()]} {text[match.end() :]}"
            title = re.sub(r"\s+", " ", rest).strip(" .,-—:")
            return title, Episode(int(match.group("season")), int(match.group("episode")))
    return text.strip(), None
