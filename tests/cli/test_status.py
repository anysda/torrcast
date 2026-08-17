"""Команда ``cast status``: собранный сеанс зовётся один раз, его код уходит наружу."""

from __future__ import annotations

from tests.fakes.command import FakeCommand
from torrcast.cli.status import status


def test_the_session_is_asked_once_and_its_code_is_returned() -> None:
    session = FakeCommand(result=0)

    assert status(session) == 0
    assert session.calls == 1


def test_a_failing_session_is_not_dressed_up_as_success() -> None:
    assert status(FakeCommand(result=2)) == 2
