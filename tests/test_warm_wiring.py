"""Проводка прогрева: один предмет на процесс и боевые службы за его тремя швами."""

from __future__ import annotations

import threading
import time

import web.warm_wiring as wiring
from web.warm_cache import TTL, WORKERS, WarmCache


def test_the_process_gets_one_assembled_warmer() -> None:
    """Единственное место, где прогрев видит свои службы, - эта проводка."""
    assert isinstance(wiring.WARM, WarmCache)
    assert wiring.WARM.circle is wiring._search
    assert wiring.WARM.blurbs is wiring._blurbs
    assert wiring.WARM.spawn is wiring._daemon


def test_the_live_warmer_keeps_the_measured_policy() -> None:
    """Мера прогрева названа числами в одном месте, и проводка их не переписывает."""
    assert wiring.WARM.ttl == TTL
    assert wiring.WARM.workers == WORKERS
    assert wiring.WARM.clock is time.monotonic


def test_the_background_hand_holds_nobody_at_the_exit() -> None:
    """Фон боевого прогрева - демон: выход из процесса он не задерживает."""
    seen: list[threading.Thread] = []
    done = threading.Event()

    started = threading.enumerate()
    wiring._daemon(done.set)
    assert done.wait(5.0)
    seen.extend(hand for hand in threading.enumerate() if hand not in started)

    for hand in seen:
        hand.join(5.0)
    assert all(hand.daemon for hand in seen)
