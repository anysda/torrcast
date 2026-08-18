"""Тот же запрос к Википедии, но статьи выбирает её поиск, а не мы перебором имён."""

from __future__ import annotations

from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.settings import _SEARCH_HITS


def search_params(query: str) -> dict[str, str]:
    """Тот же запрос, но статьи выбирает поиск Википедии, а не мы перебором имён."""
    return {
        **extract_params([]),
        "titles": "",
        "generator": "search",
        "gsrsearch": query,
        "gsrlimit": str(_SEARCH_HITS),
        "gsrnamespace": "0",
    }
