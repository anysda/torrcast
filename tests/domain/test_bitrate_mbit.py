"""Проверки расчёта среднего битрейта."""

from torrcast.domain.bitrate_mbit import bitrate_mbit


def test_bitrate() -> None:
    assert bitrate_mbit(1_000_000, 2) == 4.0
