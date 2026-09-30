"""Checks the warmup's mark: set inside the block only, and carried by a copied context."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

from torrcast.adapters.prowlarr.warmup import WARMUP, warmup


def test_the_mark_lives_inside_the_block_only() -> None:
    assert not WARMUP.get()
    with warmup():
        assert WARMUP.get()
    assert not WARMUP.get(), "a viewer's circle after the warmup was held as warmup"


def test_a_pool_sees_the_mark_only_in_a_copied_context() -> None:
    with warmup(), ThreadPoolExecutor(1) as pool:
        bare = pool.submit(WARMUP.get).result()
        carried = pool.submit(copy_context().run, WARMUP.get).result()
    assert (bare, carried) == (False, True)
