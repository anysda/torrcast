"""Ответ истории без единой обложки пережидает короткую тишину источника.

Холодный экземпляр встречает первые запросы к Википедии отказом 429: приговор истории
возвращался пустым, картины откладывались до конца тишины (:mod:`hass.hit_claims`), а
страница спрашивает историю один раз и оставалась без обложек до перезагрузки. Тишина
длится секунды (:data:`~torrcast.adapters.wiki.minute_budget.QUIET_AFTER_429`): кончилась
в пределах ``within`` - пачку спрашивают снова, дальше - ответ уходит как есть.

Ждёт только ряд, где не названо НИ ОДНОЙ обложки: у ряда с обложками недостающие обычно
настоящие промахи, и повтор стоил истории 5 с без единой новой картинки (замер TC-1322).
"""

from __future__ import annotations

import time
from collections.abc import Callable

from hass.hit_ask import _about, _name
from hass.hit_claims import _ATTEMPTS, HitClaims
from torrcast.domain.json_value import JsonValue

#: Сколько ответ истории готов ждать конца тишины источника, секунды.
WITHIN = 8.0

Offer = Callable[[], list[JsonValue]]
#: Как ждать конца тишины; тест подменяет часами, а не сном.
_pause: Callable[[float], None] = time.sleep


def _ends(owner: HitClaims, names: list[str]) -> float | None:
    """Конец тишины у отложенных отказом картин ряда без обложек; ``None`` - ждать нечего."""
    if any(owner.named(name) for name in names):
        return None
    with owner._lock:
        ends = [owner._again[name][1] for name in names if name in owner._again]
    return min(ends, default=None)


def quiet_wait(
    owner: HitClaims,
    results: list[JsonValue],
    offer: Offer,
    within: float = WITHIN,
) -> list[JsonValue]:
    """Ответ ``offer``; ряд без обложек, отложенный тишиной, что кончится вовремя, - снова."""
    answer = offer()
    names = [_name(ask) for ask in map(_about, results) if ask is not None]
    deadline = owner._now() + within
    for _ in range(_ATTEMPTS):
        ends = _ends(owner, names)
        if ends is None or ends > deadline:
            break
        pause = ends - owner._now()
        if pause > 0:
            _pause(pause)
        answer = offer()
    return answer


__all__ = ["WITHIN", "quiet_wait"]
