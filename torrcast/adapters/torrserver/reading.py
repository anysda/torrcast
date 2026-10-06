"""Идёт ли сейчас чей-то показ: читает ли кто-нибудь раздачу из службы.

Подъём службы (:mod:`.engine_restart`) спрашивает это ДО того, как убить её. Показ идёт в
своём процессе (юнит показа), поэтому видно его только со стороны службы: у раздачи,
которую показ читает, ``Readers`` в ``POST /cache`` не пуст (стенд: два читателя весь показ).

Вопросов тут 1+N, по одному на раздачу, и каждый вправе идти секунды: служба, повисшая на
``add``, отвечает медленно. Поэтому перед каждым спрашивается ``stop``: кончился срок
решения или человек отказался - ответ ``None``, «служба не сказала».
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

from torrcast.domain.infra_error import InfraError

#: ``stat`` раздачи, которая лежит только в базе службы: её никто не читает.
IN_DB: Final = 5

#: Пора ли бросить опрос: срок решения кончился или человек отказался.
type Stop = Callable[[], bool]


def _never() -> bool:
    return False


def reading(post: Callable[[str, dict[str, Any]], Any], stop: Stop = _never) -> bool | None:
    """Читает ли кто-нибудь раздачу службы прямо сейчас; ``None`` - служба не сказала."""
    try:
        if stop():
            return None
        listed = post("/torrents", {"action": "list"})
        if not isinstance(listed, list):
            return None
        for item in listed:
            if not isinstance(item, dict) or not item.get("hash") or item.get("stat") == IN_DB:
                continue
            if stop():
                return None
            state = post("/cache", {"action": "get", "hash": item["hash"]})
            readers = state.get("Readers") if isinstance(state, dict) else None
            if isinstance(readers, list) and readers:
                return True
    except InfraError:
        return None
    return False


__all__ = ["Stop", "reading"]
