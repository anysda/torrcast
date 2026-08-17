"""Прогрев не трогается с места, пока у показа нет запаса, но и не ждёт вечно."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import warmer, world
from torrcast.usecases.warm.settings import GUARD_HIGH, START_GRACE
from torrcast.usecases.warm.wait_for_picture import _wait_for_picture

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def test_a_ready_reserve_lets_the_warming_start_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запас уже есть - ждать нечего: путь до картинки дорожать не имеет права."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path, slack=GUARD_HIGH + 1.0)

    _wait_for_picture(warm)

    assert fake.slept == [], "прогрев поспал при готовом запасе"


def test_without_a_reserve_the_warming_waits_out_its_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запаса нет - стоим, но не дольше своего потолка: mock и молчащий приёмник тоже бывают."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path, slack=1.0)

    _wait_for_picture(warm)

    assert fake.slept and sum(fake.slept) >= START_GRACE, "ожидание кончилось раньше срока"
    assert sum(fake.slept) < START_GRACE + 1.0, "прогрев ждёт картинки дольше потолка"


def test_a_stopped_show_ends_the_wait_immediately(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Показ сняли - прогреву ждать картинку незачем."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path, slack=0.0)
    warm.stopped = True

    _wait_for_picture(warm)

    assert fake.slept == []
