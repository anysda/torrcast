"""Строка прогрева для человека: четыре разных ответа и ни одного расплывчатого."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from tests.usecases.warm.world import lay, vault, warmer
from torrcast.usecases.warm.line import _line

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@dataclass
class _Rival:
    working: bool = False


def _hms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_state, "_hms", lambda seconds: f"{seconds:.0f}с")


def test_a_working_warming_says_it_keeps_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Штатный ход: сколько прогрето, из скольких и что работа идёт."""
    _hms(monkeypatch)
    warm = warmer(tmp_path)
    lay(warm.vault, 0)

    assert _line(warm) == "прогрето 10с из 60с - грею дальше"


def test_a_frozen_warming_names_the_reason_it_stands(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Замерший прогрев обязан назвать, кому уступил: перекоду или самому показу."""
    _hms(monkeypatch)
    warm = warmer(tmp_path)
    warm.idle = True

    assert _line(warm).endswith("(жду запаса показа)")

    warm.rival = _Rival(working=True)
    assert _line(warm).endswith("(уступил перекоду)")


def test_a_stalled_warming_says_what_stopped_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Причина остановки идёт в строку целиком: молчаливый стоп уже стоил расследования."""
    _hms(monkeypatch)
    warm = warmer(tmp_path)
    warm.trouble = "бюджет диска исчерпан"

    assert _line(warm) == "прогрето 0с из 60с - прогрев встал: бюджет диска исчерпан"


def test_a_finished_warming_promises_life_without_the_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Весь фильм на диске - и строка говорит ровно это, а не «грею дальше»."""
    _hms(monkeypatch)
    warm = warmer(tmp_path)
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    assert _line(warm) == "прогрето 60с из 60с - фильм целиком на диске, интернет больше не нужен"


def test_the_next_episode_gets_its_own_half_of_the_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Цепочка серий видна одной строкой: своя доля и доля соседа."""
    _hms(monkeypatch)
    warm = warmer(tmp_path)
    warm.after = warmer(tmp_path, vault=vault(tmp_path, key="следующая"))
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    assert _line(warm).endswith("; следующая: прогрето 0с из 60с - грею дальше")
