"""Проверяет, когда в заблокированный индексер пора стучаться, а когда нельзя."""

import time
from datetime import UTC, datetime, timedelta

from torrcast.domain.heal_due import HEAL_PAUSE, heal_due


def _ago(seconds: float) -> str:
    """Отметка глазами Prowlarr: UTC с ``Z``. Отрицательные секунды - будущее."""
    return (datetime.now(UTC) - timedelta(seconds=seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def test_отдохнувший_отказ_с_истёкшей_отсрочкой_лечим() -> None:
    now = time.time()
    assert heal_due(_ago(HEAL_PAUSE + 240), _ago(HEAL_PAUSE + 240), now)


def test_свежий_отказ_проверками_не_добиваем() -> None:
    """Лишний запрос к трекеру - ровно та причина, по которой Prowlarr раздаёт баны."""
    now = time.time()
    assert not heal_due(_ago(1), _ago(1), now)


def test_действующую_отсрочку_стуком_не_продлеваем() -> None:
    """Мёртвому источнику Prowlarr назначает сутки и каждым POST начинает их заново."""
    now = time.time()
    assert not heal_due(_ago(300), _ago(-24 * 60 * 60), now)


def test_непрочитанное_время_отказа_лечению_не_мешает() -> None:
    """Не полечить вовсе хуже, чем сходить лишний раз."""
    now = time.time()
    assert heal_due("не время вовсе", "", now)
