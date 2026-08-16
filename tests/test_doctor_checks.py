"""Совместимый набор системных проб сохраняет прежний вход."""

from torrcast import doctor_checks


def test_doctor_checks_keeps_checkup() -> None:
    assert callable(doctor_checks.checkup)
