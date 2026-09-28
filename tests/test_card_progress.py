"""Индикатор отбора карточки: снятый прогрев выходит из отбора, живой зовёт свой индикатор."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from web.card_progress import CardProgress


class _Inner:
    def __init__(self) -> None:
        self.phases: list[str] = []

    def phase(self, text: str) -> None:
        self.phases.append(text)


def test_a_live_selection_reports_its_phase() -> None:
    inner = _Inner()

    CardProgress(inner, threading.Event()).phase("метаданные")  # type: ignore[arg-type]

    assert inner.phases == ["метаданные"]


def test_a_stopped_warm_up_leaves_the_selection_at_the_next_phase() -> None:
    halt = threading.Event()
    inner: Any = _Inner()
    halt.set()

    with pytest.raises(CardProgress.stopped):
        CardProgress(inner, halt).phase("метаданные")
    assert inner.phases == []
