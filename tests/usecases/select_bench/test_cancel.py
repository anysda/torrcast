"""Отмена идущего отбора: stop должен дойти до ожидания раздачи."""

from __future__ import annotations

import threading
import time

import pytest

from tests.usecases.select_bench.world import RUNTIME, Said, Torrents, plan, probes, rel
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.media import Media
from torrcast.ports.abandon import slot as abandon_slot
from torrcast.usecases.select_bench.bench import Bench


@pytest.mark.machine
def test_stop_interrupts_a_release_wait_before_it_can_be_selected() -> None:
    """Медленный источник не держит stop до своего ответа и не доходит до выбора."""
    release = rel(name="slow | Дубляж", seeders=10)
    answer = probes(
        [release],
        Media(
            RUNTIME,
            (AudioTrack(index=0, language="rus"),),
            "h264",
            height=1080,
            width=1920,
        ),
    )
    entered, let_finish, stopped = threading.Event(), threading.Event(), threading.Event()

    def slow(source_url: str, /, timeout: float = 90.0, alive: object = None) -> Media:
        entered.set()
        let_finish.wait(3.0)
        return answer(source_url, timeout=timeout, alive=alive)

    bench = Bench(Torrents(), prober=slow)
    abandon_slot.install(stopped.is_set)

    def stop_inside_wait() -> None:
        assert entered.wait(1.0), "отбор не дошёл до медленного ответа источника"
        stopped.set()

    stopper = threading.Thread(target=stop_inside_wait)
    stopper.start()
    began = time.monotonic()
    try:
        with pytest.raises(CancelledError):
            bench.resolve(plan([release]), Args(query=["кино"]), Said())
        elapsed = time.monotonic() - began
    finally:
        let_finish.set()
        stopper.join(timeout=1.0)
        for prep in bench.preps.values():
            prep.ready.wait(1.0)
        bench.drop_all()

    assert elapsed < 1.0, f"stop ждал ответа источника {elapsed:.2f} с"
