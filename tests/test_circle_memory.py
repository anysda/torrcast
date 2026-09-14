"""Память кругов: находка на срок, отказ на минуту, пустое не находка."""

from __future__ import annotations

from typing import Any, cast

from torrcast.domain.not_found_error import NotFoundError
from web.circle_memory import EMPTY_TTL, CircleMemory


def test_a_refusal_lives_a_minute_and_a_later_find_replaces_it() -> None:
    """Отказ помнится минуту, свежая находка его снимает, пустая находка не пишется."""
    now = [0.0]
    memory = CircleMemory(clock=lambda: now[0], ttl=300.0)
    plan = cast(Any, object())

    memory.refuse(" Lost ", NotFoundError("nothing"))
    memory.keep("Lost", [])

    assert memory.plans("Lost") == []
    assert isinstance(memory.refusal("Lost"), NotFoundError)
    memory.keep("Lost", [plan])
    assert memory.plans("Lost ") == [plan]
    assert memory.refusal("Lost") is None
    now[0] += 301.0
    assert memory.plans("Lost") is None
    memory.refuse("Lost", NotFoundError("nothing"))
    now[0] += EMPTY_TTL + 1.0
    assert memory.plans("Lost") is None
