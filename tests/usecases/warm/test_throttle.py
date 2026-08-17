"""Уступка живому показу: замереть сигналом, ожить по гистерезису и по выдержке."""

from __future__ import annotations

import signal
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from tests.usecases.warm.world import warmer, world
from torrcast.usecases.warm.settings import GUARD_HIGH, GUARD_LOW, STARVE_GRACE
from torrcast.usecases.warm.throttle import _may_resume, _resume, _throttle

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


@dataclass
class _Process:
    signals: list[int] = field(default_factory=list)

    def send_signal(self, number: int) -> None:
        self.signals.append(number)


@dataclass
class _Packer:
    proc: _Process = field(default_factory=_Process)


@dataclass
class _Rival:
    working: bool = False


def test_a_thin_reserve_freezes_the_run_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Замирает именно процесс, и ровно один раз: снятый прогон стоил бы дыры в звуке."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path, slack=GUARD_LOW - 1.0)
    packer = _Packer()

    _throttle(warm, packer)
    _throttle(warm, packer)

    assert packer.proc.signals == [signal.SIGSTOP], "прогрев замер дважды или не замер вовсе"
    assert warm.idle and fake.named("прогрев замер")["перекод"] is False


def test_a_recovered_reserve_wakes_the_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Отпустило - оживаем тем же сигналом, с того же кадра."""
    world(monkeypatch)
    warm = warmer(tmp_path, slack=GUARD_HIGH + 1.0)
    warm.idle = True
    packer = _Packer()

    _throttle(warm, packer)

    assert packer.proc.signals == [signal.SIGCONT] and not warm.idle


def test_a_tight_but_healthy_show_needs_the_grace_before_waking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запас над порогом стопа обязан ДЕРЖАТЬСЯ: разовое касание прогрев не оживляет."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path, slack=GUARD_LOW + 1.0)
    warm.idle = True

    assert _may_resume(warm) is False, "прогрев ожил от одного касания над порогом"
    assert warm.healthy_since == fake.now

    fake.now += STARVE_GRACE - 0.1
    assert _may_resume(warm) is False, "выдержка кончилась раньше срока"

    fake.now += 0.2
    assert _may_resume(warm) is True, "здоровый, но тесный показ так и не оживил прогрев"


def test_a_real_drop_resets_the_grace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Просевший запас обнуляет выдержку: живой показ всегда важнее работы впрок."""
    fake = world(monkeypatch)
    warm = warmer(tmp_path, slack=GUARD_LOW + 1.0)
    warm.idle = True
    _may_resume(warm)
    fake.now += STARVE_GRACE

    warm.slack = GUARD_LOW - 1.0
    assert _may_resume(warm) is False and warm.healthy_since == 0.0

    warm.slack = GUARD_LOW + 1.0
    assert _may_resume(warm) is False, "выдержка не начиналась заново"


def test_an_unmeasured_reserve_wakes_the_warming_at_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запаса не мерили вовсе - держать прогрев замершим не за что."""
    world(monkeypatch)
    warm = warmer(tmp_path, slack=0.0)
    warm.idle = True

    assert _may_resume(warm) is True


def test_a_running_recoder_outlives_any_reserve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пока идёт чужой заход, ничто не оживляет прогрев: ни запас, ни выдержка."""
    world(monkeypatch)
    warm = warmer(tmp_path, slack=GUARD_HIGH + 100.0)
    warm.rival = _Rival(working=True)
    packer = _Packer()

    _throttle(warm, packer)
    _throttle(warm, packer)

    assert packer.proc.signals == [signal.SIGSTOP], "прогрев ожил посреди чужого захода"


def test_waking_a_run_that_never_froze_sends_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Не замирал - и оживлять нечего: лишний сигнал живому ffmpeg не нужен."""
    world(monkeypatch)
    warm = warmer(tmp_path)
    packer = _Packer()

    _resume(warm, packer)

    assert packer.proc.signals == []
