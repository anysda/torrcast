"""Сколько добор справки живёт всего на нынешнем языке; зовёт его справка к меню."""

from __future__ import annotations

from torrcast.domain.facts.facts_budget import _spoken_wave
from torrcast.domain.facts.settings import TOPUP_LIMIT


def topup_limit() -> float:
    """Сколько добор живёт ВСЕГО на нынешнем языке, секунды; считается от старта добора.

    Растёт той же доплатой и по той же причине: не дорасти ему - поток добора умирал бы
    на третьем шаге, кэш оставался бы пустым, и КАЖДОЕ английское меню шло бы в сеть за
    тем же самым заново и снова печаталось голым.
    """
    return TOPUP_LIMIT + _spoken_wave()
