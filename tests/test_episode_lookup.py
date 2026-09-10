"""EpisodeLookup: разбор выбранной раздачи в фоне, кэш на процесс, TorrServer убран за собой."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.fakes.torrent_engines import FakeTorrentEngines
from torrcast.domain.release import Release
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.torr_file import TorrFile
from web.episode_lookup import RETRY, EpisodeLookup

_RELEASE = Release(raw_name="Show s01 WEB-DL 1080p LostFilm", title="Show", magnet="magnet:show")
_FILES = [
    TorrFile(0, "Show/Show.s01e01.mkv", 700_000_000),
    TorrFile(1, "Show/Show.s01e02.mkv", 700_000_000),
]


@dataclass
class _BoomEngine(FakeTorrentEngine):
    """Та же подделка, но добавить раздачу не выходит - служба раздач лежит."""

    def add(self, magnet: str) -> str:
        raise ServerDownError("torrserver_down")


def _sync(job: Callable[[], None]) -> None:
    job()


@dataclass
class _Clock:
    """Часы, которые двигает сама проба: срок ряда проверяется без единой секунды сна."""

    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def test_the_first_ask_starts_the_background_build_and_answers_none_when_still_slow() -> None:
    """Фон не успевает - вопрос честно висит: ``None``, а не выдуманный список."""
    engines = FakeTorrentEngines(FakeTorrentEngine(torrent_files=_FILES))
    lookup = EpisodeLookup(engines=engines, spawn=lambda _job: None)

    table = lookup.table(_RELEASE, "http://torrserver")

    assert table is None


def test_a_synchronous_build_answers_the_very_same_call_with_the_parsed_table() -> None:
    """Фон синхронный (тест) - таблица серий готова уже к первому ответу."""
    engine = FakeTorrentEngine(torrent_hash="hash-magnet:show", torrent_files=_FILES)
    lookup = EpisodeLookup(engines=FakeTorrentEngines(engine), spawn=_sync)

    table = lookup.table(_RELEASE, "http://torrserver")

    assert table is not None
    assert [row[:2] for row in table] == [[1, 1], [1, 2]]
    assert engine.added == ["magnet:show"]
    assert engine.dropped == ["hash-magnet:show"]


def test_the_cached_table_answers_the_next_ask_without_touching_the_engine_again() -> None:
    """Второй вопрос о той же раздаче не зовёт службу заново - ответ уже в кэше."""
    engines = FakeTorrentEngines(FakeTorrentEngine(torrent_files=_FILES))
    lookup = EpisodeLookup(engines=engines, spawn=_sync)
    lookup.table(_RELEASE, "http://torrserver")

    lookup.table(_RELEASE, "http://torrserver")

    assert len(engines.asked) == 1


def test_a_torrserver_failure_falls_back_to_an_empty_table_not_a_crash() -> None:
    """Служба раздач упала - таблица пуста, а не исключение наружу карточки."""
    engine = _BoomEngine(torrent_files=_FILES)
    lookup = EpisodeLookup(engines=FakeTorrentEngines(engine), spawn=_sync)

    table = lookup.table(_RELEASE, "http://torrserver")

    assert table == []
    assert engine.dropped == []


def test_a_pending_build_is_not_started_twice_for_the_same_magnet() -> None:
    """Второй вопрос, пока фон ещё бежит, не заводит второй параллельный разбор."""
    spawned: list[Callable[[], None]] = []
    lookup = EpisodeLookup(
        engines=FakeTorrentEngines(FakeTorrentEngine(torrent_files=_FILES)),
        spawn=spawned.append,
    )
    lookup.table(_RELEASE, "http://torrserver")

    lookup.table(_RELEASE, "http://torrserver")

    assert len(spawned) == 1


def test_a_parsed_release_is_never_asked_again_but_a_failed_one_is() -> None:
    """Разбор ответил - ответ окончателен; служба лежала - через :data:`RETRY` спросят снова.

    Обе беды кончались одной пустой таблицей с одним сроком, и по его выходе налитая
    карточка снова просила страницу переспросить (замер 10-09-2026 на стенде `.104`).
    """
    clock = _Clock()
    whole = FakeTorrentEngines(FakeTorrentEngine(torrent_files=_FILES))
    down = FakeTorrentEngines(_BoomEngine(torrent_files=_FILES))
    parsed = EpisodeLookup(engines=whole, spawn=_sync, clock=clock)
    fallen = EpisodeLookup(engines=down, spawn=_sync, clock=clock)
    parsed.table(_RELEASE, "http://torrserver")
    fallen.table(_RELEASE, "http://torrserver")
    clock.now += RETRY + 1

    parsed.table(_RELEASE, "http://torrserver")
    fallen.table(_RELEASE, "http://torrserver")

    assert len(whole.asked) == 1, "разобранное не протухает: содержимое раздачи не меняется"
    assert len(down.asked) == 2, "неудачу спрашивают заново - рой мог ожить"
