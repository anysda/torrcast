"""Зеркало :mod:`torrcast.usecases.doctor_command`: печать самопроверки и её вердикт."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_OK
from torrcast.ports.health_config import HealthConfig
from torrcast.usecases import doctor_command
from torrcast.usecases.doctor_command import _cmd_doctor


def _answers(*lines: tuple[str, bool]) -> object:
    def checkup(config: HealthConfig) -> Iterator[tuple[str, bool]]:
        yield from lines

    return checkup


def test_a_healthy_household_is_an_honest_zero(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Ноль от самопроверки - договор командной строки, и меняться он не вправе."""
    monkeypatch.setattr(doctor_command, "checkup", _answers(("ок      ffmpeg", True)))

    assert _cmd_doctor() == EXIT_OK
    lines = ["ок      ffmpeg", "", phrase("doctor.all_clear")]
    assert capsys.readouterr().out.splitlines() == lines


def test_a_broken_household_answers_two_and_says_how_many(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Двойка на нездоровом хозяйстве - тот же договор, и число проблем печатается."""
    monkeypatch.setattr(
        doctor_command, "checkup", _answers(("плохо   ТВ", False), ("плохо   ffmpeg", False))
    )

    assert _cmd_doctor() == EXIT_INFRA
    assert phrase("doctor.problems", bad=2) in capsys.readouterr().out


def test_one_bad_line_among_good_ones_is_enough_to_fail(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Хорошее большинство вердикта не спасает: сломанное звено сужает показ."""
    monkeypatch.setattr(
        doctor_command, "checkup", _answers(("ок      ffmpeg", True), ("плохо   ТВ", False))
    )

    assert _cmd_doctor() == EXIT_INFRA
    assert phrase("doctor.problems", bad=1) in capsys.readouterr().out
