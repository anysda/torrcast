"""Схема ``warm/plan``: чем кодируют куски живая упаковка и прогрев."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.plan import plan


def test_both_producers_are_named_in_one_record_so_their_disagreement_is_visible(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Запись существует ради одного вопроса: одинаково ли решают два производителя.

    Разъедься решение упаковки и прогрева - это видно строкой в разборе, а не разбором
    аргументов ffmpeg постфактум. Поэтому оба стоят в ОДНОЙ записи.
    """
    seen = caught(monkeypatch)

    plan(pack="recode", warm="copy", spots=88, preset="veryfast", mbit=12.345)

    assert seen == [
        (
            "warm",
            "plan",
            {"pack": "recode", "warm": "copy", "spots": 88, "preset": "veryfast", "mbit": 12.35},
        )
    ]


def test_a_show_without_a_preset_still_writes_the_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """Показ копией пресета не называет - но запись плана всё равно обязана быть."""
    seen = caught(monkeypatch)

    plan(pack="copy", warm="copy", spots=0)

    assert seen[0][2] == {"pack": "copy", "warm": "copy", "spots": 0, "preset": "", "mbit": 0.0}
