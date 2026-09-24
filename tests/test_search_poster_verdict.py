"""One owner judges a search list's posters and releases the lock on every exit."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from hass.search_job import SearchJob


def test_a_failed_preview_poster_verdict_releases_the_job() -> None:
    """The preview worker owns the verdict until failure, then another poll may retry."""

    def fail(_records: list[Any]) -> list[Any]:
        raise RuntimeError("preview verdict fell")

    job = SearchJob()
    assert job._claim_verdict(), "the test worker must own the verdict it is about to run"
    with pytest.raises(RuntimeError, match="preview verdict fell"):
        job._judge_alone([{"key": "movie"}], fail)

    assert job.judging is False


@pytest.mark.machine
def test_two_preview_polls_start_exactly_one_verdict_for_one_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two readers that both observed an idle job must not judge the same list twice."""
    readers = threading.Barrier(2)
    verdict_started = threading.Event()
    verdict_release = threading.Event()
    calls: list[list[Any]] = []

    class RacingJob(SearchJob):
        def __getattribute__(self, name: str) -> Any:
            value = super().__getattribute__(name)
            if name == "judging" and threading.current_thread().name.startswith("reader-"):
                readers.wait(2.0)
            return value

    def offer(records: list[Any]) -> list[Any]:
        calls.append(records)
        verdict_started.set()
        verdict_release.wait(2.0)
        return records

    job = RacingJob()
    hits: list[Any] = [{"key": "movie"}]
    real_thread = threading.Thread
    polls = [
        real_thread(target=job.dress, args=(hits, offer), name=f"reader-{number}")
        for number in range(2)
    ]
    workers: list[threading.Thread] = []

    class TrackingThread:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            self.thread = real_thread(*args, **kwargs)

        def start(self) -> None:
            workers.append(self.thread)
            self.thread.start()

    monkeypatch.setattr("hass.search_poster_verdict.threading.Thread", TrackingThread)
    for poll in polls:
        poll.start()
    assert verdict_started.wait(2.0)
    verdict_release.set()
    for poll in polls:
        poll.join(2.0)
    for worker in workers:
        worker.join(2.0)

    assert len(calls) == 1, f"one list received {len(calls)} poster verdicts"


__all__: list[str] = []
