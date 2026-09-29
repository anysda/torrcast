"""Держатель заводит раздачи истории по одной, первой - названную страницей первой."""

from __future__ import annotations

from tests.fakes.state_store import FakeStateStore
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.test_record_hold import _entry, _live, _Page, state
from web.record_hold import COLD, MUTE

__all__ = ["state"]


def test_the_next_release_waits_until_the_one_before_answered(state: FakeStateStore) -> None:
    """Двадцать раздач разом тянули метаданные живой 15-19 с вместо 0.2-3."""
    engine = _live()
    page = _Page({"a": _entry("magnet:a"), "b": _entry("magnet:b")}, engine)
    page.holder.touch("http://ts", ["a", "b"])

    page.spawned.pop(1)()  # «b» пошёл раньше, но «a» ещё не ответила

    assert engine.added == []


def test_the_key_the_page_names_first_goes_first(state: FakeStateStore) -> None:
    """Карточку, открытую над главной, её раздача не ждёт за плитками истории."""
    engine = _live()
    page = _Page({"a": _entry("magnet:a"), "b": _entry("magnet:b")}, engine)
    page.holder.touch("http://ts", ["a", "b"])
    page.holder.touch("http://ts", ["b", "a"])

    page.spawned.pop(1)()

    assert engine.added[0] == "magnet:b"


def test_a_release_without_peers_is_let_go_and_left_alone_for_a_while(
    state: FakeStateStore,
) -> None:
    engine = FakeTorrentEngine()  # служба ответила, метаданных нет
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])

    page.run()

    assert engine.added == ["magnet:a"]
    assert engine.dropped == ["hash"]
    assert COLD <= page.now < 2 * COLD
    assert page.holder.touch("http://ts", ["a"]) == 0
    page.now += MUTE
    assert page.holder.touch("http://ts", ["a"]) == 1
