"""Проверяет recent_enough: окно ленты считается назад от текущего часа."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from torrcast.domain.recent_enough import recent_enough

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=UTC)


def test_a_raid_inside_the_window_is_recent_enough() -> None:
    """Раздача внутри окна проходит: 13 дней назад укладываются в 14-дневное окно."""
    assert recent_enough(NOW - timedelta(days=13), NOW, days=14) is True


def test_a_raid_older_than_the_window_is_not_recent_enough() -> None:
    """Раздача старше окна не проходит: 15 дней назад не укладываются в 14-дневное окно."""
    assert recent_enough(NOW - timedelta(days=15), NOW, days=14) is False


def test_a_clock_ahead_of_ours_is_still_recent_enough() -> None:
    """Часы Prowlarr нам не подчинены: раздача из будущего - всё равно самая свежая."""
    assert recent_enough(NOW + timedelta(minutes=1), NOW, days=14) is True
