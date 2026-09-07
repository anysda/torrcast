"""Проверяет SourcesCache: число источников строится фоном, читается мгновенно."""

from __future__ import annotations

import pytest

from torrcast.domain.infra_error import InfraError
from web.sources_cache import Count, SourcesCache, Spawn


def _cache(*, count: Count | None = None, spawn: Spawn | None = None) -> SourcesCache:
    return SourcesCache(count=count or (lambda: 7), spawn=spawn or (lambda job: None))


def test_before_the_first_build_the_count_is_zero_not_blocking() -> None:
    """Фон ещё не бегал - число честно ноль, а не выдумано из воздуха."""
    assert _cache().get() == 0


def test_rebuild_fills_the_count_from_the_roster() -> None:
    cache = _cache(count=lambda: 5)

    cache._rebuild()

    assert cache._value == 5


def test_a_broken_roster_does_not_crash_the_rebuild() -> None:
    """Отказ Prowlarr (InfraError у ``known()``) не роняет фон - следующий час свой."""

    def failing_count() -> int:
        raise InfraError("прибили")

    cache = _cache(count=failing_count)

    cache._rebuild()  # не должно бросить наружу

    assert cache._value == 0


def test_get_starts_the_background_loop_exactly_once() -> None:
    calls: list[object] = []
    cache = _cache(spawn=lambda job: calls.append(job))

    cache.get()
    cache.get()
    cache.get()

    assert len(calls) == 1


def test_the_loop_rebuilds_then_sleeps_for_the_configured_period() -> None:
    build_count = 0

    def counting_count() -> int:
        nonlocal build_count
        build_count += 1
        return 3

    slept: list[float] = []

    def stopping_sleep(seconds: float) -> None:
        slept.append(seconds)
        raise RuntimeError("stop the loop for the test")

    cache = SourcesCache(
        count=counting_count,
        spawn=lambda job: None,
        sleep=stopping_sleep,
        every=3600.0,
    )

    with pytest.raises(RuntimeError, match="stop the loop"):
        cache._loop()

    assert build_count == 1
    assert slept == [3600.0]
