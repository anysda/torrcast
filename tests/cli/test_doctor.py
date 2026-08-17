"""Команда ``cast doctor``: самопроверка зовётся один раз, её вердикт уходит наружу."""

from __future__ import annotations

from tests.fakes.command import FakeCommand
from torrcast.cli.doctor import doctor


def test_the_checkup_is_asked_once_and_its_code_is_returned() -> None:
    checkup = FakeCommand(result=0)

    assert doctor(checkup) == 0
    assert checkup.calls == 1


def test_a_bad_checkup_stays_an_infrastructure_failure() -> None:
    assert doctor(FakeCommand(result=2)) == 2
