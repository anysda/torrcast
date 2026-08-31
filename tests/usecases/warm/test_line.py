"""Строка прогрева для человека: четыре разных ответа и ни одного расплывчатого."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, vault, warmer, world
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.warm.line import _line

if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class _Rival:
    working: bool = False


def _hms(seconds: float) -> str:
    """Часы прогрева коротко: в строке важен не формат, а числа рядом с ним."""
    return f"{seconds:.0f}с"


def test_a_working_warming_says_it_keeps_going(tmp_path: Path) -> None:
    """Штатный ход: сколько прогрето, из скольких и что работа идёт."""
    world(clock_face=_hms)
    warm = warmer(tmp_path)
    lay(warm.vault, 0)

    head = phrase("warm.progress_head", warmed="10с", duration="60с")
    assert _line(warm) == phrase("warm.warming_on", head=head)


def test_a_frozen_warming_names_the_reason_it_stands(tmp_path: Path) -> None:
    """Замерший прогрев обязан назвать, кому уступил: перекоду или самому показу."""
    world(clock_face=_hms)
    warm = warmer(tmp_path)
    warm.idle = True

    assert _line(warm).endswith(f"({phrase('warm.waiting_slot')})")

    warm.rival = _Rival(working=True)
    assert _line(warm).endswith(f"({phrase('warm.busy_rival')})")


def test_a_stalled_warming_says_what_stopped_it(tmp_path: Path) -> None:
    """Причина остановки идёт в строку целиком: молчаливый стоп уже стоил расследования."""
    world(clock_face=_hms)
    warm = warmer(tmp_path)
    warm.trouble = "бюджет диска исчерпан"

    head = phrase("warm.progress_head", warmed="0с", duration="60с")
    assert _line(warm) == phrase("warm.trouble_note", head=head, trouble=warm.trouble)


def test_a_finished_warming_promises_life_without_the_network(tmp_path: Path) -> None:
    """Весь фильм на диске - и строка говорит ровно это, а не «грею дальше»."""
    world(clock_face=_hms)
    warm = warmer(tmp_path)
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    head = phrase("warm.progress_head", warmed="60с", duration="60с")
    assert _line(warm) == phrase("warm.done_note", head=head)


def test_the_next_episode_gets_its_own_half_of_the_line(tmp_path: Path) -> None:
    """Цепочка серий видна одной строкой: своя доля и доля соседа."""
    world(clock_face=_hms)
    warm = warmer(tmp_path)
    warm.after = warmer(tmp_path, vault=vault(tmp_path, key="следующая"))
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    next_head = phrase("warm.progress_head", warmed="0с", duration="60с")
    next_line = phrase("warm.warming_on", head=next_head)
    assert _line(warm).endswith(phrase("warm.next_note", done="", next=next_line))
