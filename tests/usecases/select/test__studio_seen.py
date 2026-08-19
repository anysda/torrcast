"""Проверки памяти студии картины."""

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.select._studio_seen import _studio_seen

ENTRY = Entry(title="Харли Квинн", magnet="magnet:?x", kind="tv", studio="The Kitchen Russia")


def test_memory_comes_from_the_picture_key() -> None:
    state = WatchState(entries={"tv:harley-quinn:2019": ENTRY})
    assert _studio_seen(state, "tv:harley-quinn:2019") == "The Kitchen Russia"


def test_record_found_by_query_is_the_spare_one() -> None:
    state = WatchState(entries={"tv:harley-quinn:2019": ENTRY})
    assert _studio_seen(state, "tv:other:2020", ("tv:harley-quinn:2019", ENTRY)) == (
        "The Kitchen Russia"
    )


def test_no_record_no_memory() -> None:
    assert _studio_seen(WatchState(), "tv:harley-quinn:2019") == ""
