"""Держатель заводит раздачи истории по одной, первой - названную страницей первой."""

from __future__ import annotations

from tests.fakes.state_store import FakeStateStore
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.test_record_hold import _entry, _live, _Page, state
from web.record_hold import COLD, LEASE, MUTE
from web.record_warm import RecordWarm

__all__ = ["state"]


class _Beyond(RecordWarm):
    """Записи дальше первых в ряду: их не греют, и очередь они ждут."""

    def wants(self, magnet: str) -> bool:
        return False


def test_the_next_release_waits_until_the_one_before_answered(state: FakeStateStore) -> None:
    """Двадцать раздач разом тянули метаданные живой 15-19 с вместо 0.2-3."""
    engine = _live()
    page = _Page({"a": _entry("magnet:a"), "b": _entry("magnet:b")}, engine, _Beyond())
    page.holder.touch("http://ts", ["a", "b"])

    page.spawned.pop(1)()  # «b» пошёл раньше, но «a» ещё не ответила

    assert engine.added == []


def test_a_first_record_of_the_row_does_not_wait_for_the_queue(state: FakeStateStore) -> None:
    """Её байты греются до клика, а очередь держала её за мёртвой соседкой до 20 с."""
    engine = _live()
    page = _Page({"a": _entry("magnet:a"), "b": _entry("magnet:b")}, engine)
    page.holder.touch("http://ts", ["a", "b"])

    page.spawned.pop(1)()

    assert engine.added[0] == "magnet:b"


def test_the_key_the_page_names_first_goes_first(state: FakeStateStore) -> None:
    """Карточку, открытую над главной, её раздача не ждёт за плитками истории."""
    engine = _live()
    page = _Page({"a": _entry("magnet:a"), "b": _entry("magnet:b")}, engine, _Beyond())
    page.holder.touch("http://ts", ["a", "b"])
    page.holder.touch("http://ts", ["b", "a"])

    page.spawned.pop(1)()

    assert engine.added[0] == "magnet:b"


def test_a_release_without_peers_is_let_go_and_left_alone_for_a_while(
    state: FakeStateStore,
) -> None:
    engine = FakeTorrentEngine()  # служба ответила, метаданных нет
    page = _Page({"a": _entry("magnet:a")}, engine, _Beyond())
    page.holder.touch("http://ts", ["a"])

    page.run()

    assert engine.added == ["magnet:a"]
    assert engine.dropped == ["hash"]
    assert COLD <= page.now < 2 * COLD
    assert page.holder.touch("http://ts", ["a"]) == 0
    page.now += MUTE
    assert page.holder.touch("http://ts", ["a"]) == 1


def test_a_first_record_without_metadata_is_added_again_not_left_alone(
    state: FakeStateStore,
) -> None:
    """Заведённая снова, она отдавала метаданные за 1-2 с; заглушенная - кадра не было."""
    engine = FakeTorrentEngine()
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])

    page.run()

    assert engine.added == ["magnet:a", "magnet:a"]
    assert page.now >= LEASE
    assert page.holder.touch("http://ts", ["a"]) == 1


class _OnlyA(RecordWarm):
    def wants(self, magnet: str) -> bool:
        return magnet == "magnet:a"


def test_a_first_record_added_again_lets_the_queue_behind_it_go(state: FakeStateStore) -> None:
    """Иначе мёртвая первая держала бы остальные записи ряда до конца аренды."""
    engine = FakeTorrentEngine()
    page = _Page({"a": _entry("magnet:a"), "b": _entry("magnet:b")}, engine, _OnlyA())
    page.holder.touch("http://ts", ["a", "b"])
    behind = page.spawned.pop(1)

    def after_the_miss() -> None:
        if page.now > COLD:
            page.on_wait = lambda: None
            behind()

    page.on_wait = after_the_miss
    page.run()

    assert "magnet:b" in engine.added
