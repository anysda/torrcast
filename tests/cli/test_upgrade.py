"""Команда ``cast --upgrade``: собранный сеанс зовётся один раз, его код уходит наружу."""

from __future__ import annotations

from tests.fakes.command import FakeCommand
from torrcast.cli.upgrade import upgrade


def test_the_session_is_asked_once_and_its_code_is_returned() -> None:
    session = FakeCommand(result=0)

    assert upgrade(session) == 0
    assert session.calls == 1


def test_a_refused_upgrade_is_not_dressed_up_as_success() -> None:
    assert upgrade(FakeCommand(result=2)) == 2
