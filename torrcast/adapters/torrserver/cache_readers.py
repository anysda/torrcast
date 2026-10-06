"""Сколько читателей держит раздачу в TorrServer: ``Readers`` из ``POST /cache``."""

from collections.abc import Callable
from typing import Any

from torrcast.domain.infra_error import InfraError


def cache_readers(post: Callable[[str, dict[str, Any]], Any], torrent_hash: str) -> int:
    """Число читателей раздачи; нет раздачи, нет кэша или служба молчит - ноль.

    Ноль на отказе честен для единственного зовущего, снятия: ждать дальше нечего.
    """
    try:
        state = post("/cache", {"action": "get", "hash": torrent_hash})
    except InfraError:
        return 0
    found = state.get("Readers") if isinstance(state, dict) else None
    return len(found) if isinstance(found, list) else 0
