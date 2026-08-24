"""Отбор судит устойчивую доставку после разгона, а не случайный первый тик."""

from torrcast.domain.swarm_pick import swarm_pick


def test_pick_uses_the_warmed_window_after_settling() -> None:
    measured = swarm_pick(
        [(1.0, 0.0), (3.0, 2_000_000.0), (8.0, 22_000_000.0), (12.0, 38_000_000.0)],
        file_index=7,
        file_size=9_000_000_000,
        duration=3600.0,
        settle=3.0,
    )

    assert measured is not None
    ratio, got, need = measured
    assert ratio == 1.6 and got == 32.0 and need == 20.0


def test_one_tick_is_not_an_window() -> None:
    assert swarm_pick([(9.0, 9_000_000.0)], 0, 1_000_000, 10.0, settle=3.0) is None
