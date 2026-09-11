"""Зеркало третьего признака мёртвой записи: файлы есть, а с роем никто не поговорил."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from tests.usecases.select.dead_swarm import SILENT, Swarm
from tests.usecases.select.world import entry
from torrcast.domain.config import Config
from torrcast.domain.pick_settings import RECORDED_CONTACT
from torrcast.usecases.select._dead_release import _dead_release
from torrcast.usecases.select._voiced import _Voiced


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русский приговор записанной раздаче."""


def test_a_remembered_release_nobody_seeds_is_dead_within_the_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Файлы служба помнит из своей базы, а рой молчит: раньше такая запись проходила
    проверку мгновенно и шесть минут не давала кадра. Теперь - приговор за срок."""
    clock = FakeClock()
    composition.use_engines(monkeypatch, Swarm(talks_at=None, clock=clock))

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=clock) == SILENT
    assert clock.now <= RECORDED_CONTACT + 0.5, "приговор не позже срока"


def test_a_remembered_release_that_talks_late_still_plays(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Контакт на 20-й секунде - жива; ждали ровно до контакта, а не весь срок."""
    clock = FakeClock()
    composition.use_engines(monkeypatch, Swarm(talks_at=20.0, clock=clock))

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=clock) == ""
    assert 20.0 <= clock.now < 21.0


def test_a_service_silent_about_the_swarm_gives_no_verdict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Служба не сказала про рой ни слова - приговора нет, как нет его и у отбора."""
    clock = FakeClock()
    composition.use_engines(monkeypatch, Swarm(quiet=True, clock=clock))

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=clock) == ""


def test_a_buried_release_is_marked_with_the_reason_of_its_death(
    monkeypatch: pytest.MonkeyPatch, tape: Tape
) -> None:
    """Приговор несёт в след свою причину: по ней мёртвое отличается от молчащего."""
    clock = FakeClock()
    composition.use_engines(monkeypatch, Swarm(talks_at=None, clock=clock))

    assert _dead_release(Config(), entry(file_idx=0), _Voiced(), clock=clock) != ""

    (mark,) = tape.named("записанная раздача")
    assert mark["исход"] == "похоронена"
    assert mark["причина"] == SILENT
