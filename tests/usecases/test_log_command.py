"""Зеркально проверяет разбор границы ``cast log --since``."""

import time

import pytest

from torrcast.usecases.log_command import _cmd_log, _since_seconds


def test_no_boundary_means_the_whole_trace() -> None:
    assert _since_seconds(None) == 0.0
    assert _since_seconds("") == 0.0


def test_relative_boundaries_count_back_from_now() -> None:
    assert time.time() - _since_seconds("2d") == pytest.approx(172800.0, abs=5)
    assert time.time() - _since_seconds("12h") == pytest.approx(43200.0, abs=5)
    assert time.time() - _since_seconds("30m") == pytest.approx(1800.0, abs=5)


def test_a_date_is_read_as_local_midnight_and_junk_as_nothing() -> None:
    assert _since_seconds("2026-08-16") == time.mktime(time.strptime("2026-08-16", "%Y-%m-%d"))
    assert _since_seconds("вчера") == 0.0
    assert _cmd_log is not None
