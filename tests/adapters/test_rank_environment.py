"""Проверяет системную среду ранжирования."""

import pytest

from torrcast.adapters.rank_environment import environment


def test_rank_environment_can_write(capsys: pytest.CaptureFixture[str]) -> None:
    environment.write("готово")
    assert "готово" in capsys.readouterr().out
