"""Проверяет, что кэш полок даёт заходу всё, что тот у него берёт."""

from __future__ import annotations

from pathlib import Path

from web.pass_cache import PassCache
from web.shelves_cache import ShelvesCache


def test_the_shelves_cache_is_what_a_pass_takes(tmp_path: Path) -> None:
    cache = ShelvesCache(feed=lambda _limit: [], catalogue=None, offer=lambda r: r)  # type: ignore[arg-type]

    assert isinstance(cache, PassCache)
