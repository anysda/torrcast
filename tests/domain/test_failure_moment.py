"""Проверяет чтение отметки отказа, какой её ставит Prowlarr."""

from datetime import UTC, datetime

from torrcast.domain.failure_moment import failure_moment


def test_читает_utc_отметку_живого_стенда() -> None:
    """Время приходит видом «2026-08-09T20:13:28Z» - с ``Z``, а не со смещением."""
    when = failure_moment("2026-08-09T20:13:28Z")
    assert when == datetime(2026, 8, 9, 20, 13, 28, tzinfo=UTC).timestamp()


def test_дробную_часть_секунды_отрезает() -> None:
    """Prowlarr отдаёт её то в шесть знаков, то в семь, а семь принимают не все версии."""
    whole = failure_moment("2026-08-09T20:13:28Z")
    assert failure_moment("2026-08-09T20:13:28.123456Z") == whole
    assert failure_moment("2026-08-09T20:13:28.1234567Z") == whole


def test_непрочитанное_время_это_none_а_не_ноль() -> None:
    """Ноль был бы отметкой 1970 года, то есть враньём про давний отказ."""
    assert failure_moment("не время вовсе") is None
    assert failure_moment("") is None
