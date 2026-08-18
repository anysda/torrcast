"""Остановка прогрева: причина попадает и человеку, и в журнал, и в недельный след."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, warmer, world
from torrcast.usecases.warm.stall import _stall, _trace

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_the_reason_reaches_all_three_ears(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Молчаливая остановка уже стоила расследования: причина говорится трижды."""
    fake = world()
    said: list[str] = []
    warm = warmer(tmp_path, log=said.append)
    lay(warm.vault, 0)

    _stall(warm, "бюджет диска исчерпан")

    assert warm.trouble == "бюджет диска исчерпан", "прогрев не встал"
    assert said and "бюджет диска исчерпан" in said[-1], "человеку ничего не сказали"
    assert fake.named("прогрев встал")["причина"] == "бюджет диска исчерпан"
    assert fake.named("прогрев встал")["секунд"] == round(warm.grid.span(0))
    assert [event for event, _args, _facts in fake.events] == ["warmth"]
    assert fake.events[0][1] == ("stall",)
    assert fake.events[0][2]["why"] == "бюджет диска исчерпан"


def test_the_trace_carries_numbers_apart_and_not_a_sentence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """В след идут числа врозь: по ним и через неделю видно, сколько успел прогрев."""
    fake = world()
    warm = warmer(tmp_path)
    lay(warm.vault, 0, size=777)

    _trace(warm, "ready")

    event, args, facts = fake.events[0]
    assert (event, args) == ("warmth", ("ready",))
    assert facts["secs"] == warm.grid.span(0)
    assert facts["dur"] == warm.grid.duration
    assert facts["size"] == 777 and facts["why"] == ""
