"""A warmup's names wait for its text held in the queues; a viewer's wait their head start only."""

from __future__ import annotations

import threading
from contextlib import nullcontext

import pytest

from torrcast.adapters.prowlarr.names_head import names_head
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.warmup import warmup


def test_a_warmups_names_wait_its_text_through_the_queues() -> None:
    assert names_head(1.0) == 1.0
    with warmup():
        assert names_head(1.0) == 61.0, "the queues hold a text 60 s at most"


@pytest.mark.machine
def test_the_names_leave_behind_a_warmups_text_held_past_their_head_start() -> None:
    # Names let go beside a held text drew RuTor's slot ahead of it once a viewer took the circle.
    def answered(*, warm: bool) -> bool:
        client = Prowlarr("http://prowlarr.invalid", "key")
        leaves = threading.Timer(0.5, client._circle.sent.set)  # the text leaves the queues
        leaves.start()
        try:
            with warmup() if warm else nullcontext():
                return client.sent(0.2)
        finally:
            leaves.cancel()
            leaves.join()

    assert answered(warm=True), "a warmup's names went before its text left"
    assert not answered(warm=False), "a viewer's names waited past their head start"
