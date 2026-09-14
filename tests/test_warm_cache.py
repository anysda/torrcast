"""WarmCache: согретый круг, очередь по видимому экрану и живое вперёд фона."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.domain.server_down_error import ServerDownError
from torrcast.usecases.discover.cut_circle import CutCircle
from torrcast.usecases.discover.told_circle import ToldCircle
from torrcast.usecases.discover.told_indexer import Told
from torrcast.usecases.facts import FactPicture
from torrcast.usecases.select.plan import Plan
from web.circle_disk import CircleDisk
from web.circle_memory import EMPTY_TTL
from web.warm_cache import LIMIT, TTL, WORKERS, WarmCache

_MOVIE = Picture(title="Interstellar", year=2014, kind="movie")
_MOVIE.releases = [Release(raw_name="Interstellar 2014 BDRip 1080p", title="Interstellar")]
_PLAN = Plan(picture=_MOVIE, ranked=list(_MOVIE.releases), runtime=8520.0, warn_mbit=12.0)

#: Картина, которую полка называет одним именем, а круг поиска - другим: справка
#: спрашивается по имени круга, и прогрев обязан греть именно его.
_SHAWSHANK = Picture(
    title="Побег из Шоушенка", year=1994, kind="movie", original="The Shawshank Redemption"
)
_SHAWSHANK.releases = [Release(raw_name="The Shawshank Redemption 1994 BDRip", title="Shawshank")]
_SHOWN = Plan(picture=_SHAWSHANK, ranked=list(_SHAWSHANK.releases), runtime=8520.0, warn_mbit=12.0)


@dataclass
class _Circle:
    """Круг-счётчик: помнит, по каким запросам его звали и сколько раз."""

    answer: list[Plan] = field(default_factory=lambda: [_PLAN])
    asked: list[str] = field(default_factory=list)

    def __call__(self, query: str) -> list[Plan]:
        self.asked.append(query)
        return self.answer


def _sync(job: Callable[[], None]) -> None:
    job()


def _cache(
    circle: Callable[[str], list[Plan]],
    spawn: Callable[[Callable[[], None]], None] = _sync,
    clock: Callable[[], float] = time.monotonic,
    ttl: float = TTL,
) -> WarmCache:
    return WarmCache(
        circle=circle, blurbs=lambda _pictures: None, spawn=spawn, clock=clock, ttl=ttl
    )


def test_the_warmed_circle_answers_the_live_card_without_a_second_trip() -> None:
    """Согретое отдаётся из памяти: второго захода к индексерам живой запрос не стоит."""
    circle = _Circle()
    cache = _cache(circle)
    cache.ask(["Interstellar"])

    plans = cache.take("Interstellar")

    assert plans == [_PLAN]
    assert circle.asked == ["Interstellar"]


def test_a_stale_circle_is_asked_again_because_releases_leave_the_pool() -> None:
    """Срок вышел - круг спрашивается заново: по этим раздачам жмут «Играть»."""
    circle = _Circle()
    now = [1000.0]
    cache = _cache(circle, clock=lambda: now[0], ttl=300.0)
    cache.take("Interstellar")
    now[0] += 301.0

    cache.take("Interstellar")

    assert circle.asked == ["Interstellar", "Interstellar"]


def test_an_empty_find_is_not_remembered_as_a_warm_circle() -> None:
    """Пустая находка - не находка: иначе согретая пустота отвечала бы 404 за карточку."""
    circle = _Circle(answer=[])
    cache = _cache(circle)
    cache.take("Interstellar")

    cache.take("Interstellar")

    assert circle.asked == ["Interstellar", "Interstellar"]


def test_nothing_found_is_remembered_for_a_minute_and_not_asked_again() -> None:
    """Картина без раздач: переспрос карточки раз в секунду не гонит круг заново."""
    asked: list[str] = []
    now = [1000.0]

    def _circle(query: str) -> list[Plan]:
        asked.append(query)
        raise NotFoundError("nothing")

    cache = _cache(_circle, clock=lambda: now[0])
    cache.ask(["Ludwig"])

    assert cache.ready("Ludwig") == []
    with pytest.raises(NotFoundError):
        cache.take("Ludwig")
    cache.ask(["Ludwig"])
    assert asked == ["Ludwig"]
    now[0] += EMPTY_TTL + 1.0
    assert cache.ready("Ludwig") is None
    with pytest.raises(NotFoundError):
        cache.take("Ludwig")
    assert asked == ["Ludwig", "Ludwig"]


def test_a_screen_of_search_hits_costs_one_circle_for_the_whole_screen() -> None:
    """У выдачи запрос один на весь экран - и кругов у неё тоже один, а не по плитке."""
    circle = _Circle()
    cache = _cache(circle)

    queued = cache.ask(["kin" for n in range(7)])

    assert queued == 1
    assert circle.asked == ["kin"]


def test_a_shelf_screen_warms_every_tile_it_sees_and_only_what_it_sees() -> None:
    """Полка - запрос на плитку; невидимого в списке нет, значит и в очереди его нет."""
    circle = _Circle()
    cache = _cache(circle)

    cache.ask(["Ludwig", "Kin", "Hokum"])

    assert circle.asked == ["Ludwig", "Kin", "Hokum"]


def test_the_already_warm_screen_asks_for_nothing_at_all() -> None:
    """Человек листает туда-сюда: согретый экран второй раз в сеть не ходит."""
    circle = _Circle()
    cache = _cache(circle)
    cache.ask(["Ludwig"])

    queued = cache.ask(["Ludwig"])

    assert queued == 0
    assert circle.asked == ["Ludwig"]


def test_a_new_screen_replaces_the_queue_of_the_one_before_it() -> None:
    """Долистал дальше - греется новое: старая очередь уступает, а не встаёт впереди."""
    circle = _Circle()
    jobs: list[Callable[[], None]] = []
    cache = _cache(circle, spawn=jobs.append)
    cache.ask(["Ludwig", "Kin"])

    cache.ask(["Hokum"])
    for job in list(jobs):
        job()

    assert circle.asked == ["Hokum"]


def test_the_screen_never_puts_more_hands_on_the_indexers_than_allowed() -> None:
    """Рук у фона столько, сколько названо: пул индексеров у него общий с живым поиском."""
    jobs: list[Callable[[], None]] = []
    cache = _cache(_Circle(), spawn=jobs.append)

    cache.ask(["Ludwig", "Kin", "Hokum", "Interstellar"])

    assert len(jobs) == WORKERS


def test_a_screen_longer_than_the_ceiling_is_cut_to_the_ceiling() -> None:
    """Потолок экрана - потолок: очередь длиннее греет то, до чего не долистали."""
    circle = _Circle()
    cache = _cache(circle)

    cache.ask([f"q{n}" for n in range(LIMIT + 5)])

    assert len(circle.asked) == LIMIT


def test_the_blurbs_of_a_whole_circle_are_asked_in_one_batch_and_only_once() -> None:
    """Справка едет пакетом: двенадцать картин стоят источнику столько же, сколько одна."""
    batches: list[list[FactPicture]] = []

    def _blurbs(pictures: list[FactPicture]) -> None:
        batches.append(list(pictures))

    cache = WarmCache(circle=_Circle(answer=[_PLAN, _SHOWN]), blurbs=_blurbs, spawn=_sync)

    cache.ask(["Interstellar"])
    cache.ask(["Interstellar"])

    assert batches == [[("Interstellar", 2014, "movie"), ("Побег из Шоушенка", 1994, "movie")]]


def test_the_blurb_is_warmed_by_the_name_the_card_will_ask_by() -> None:
    """Справку карточка спрашивает по имени КАРТИНЫ, а на плитке полки надпись другая.

    Замерено на стенде: плитка звалась ``The Shawshank Redemption``, карточка искала
    ``Побег из Шоушенка``, и справка, согретая по надписи, не доставалась никому.
    """
    batches: list[list[FactPicture]] = []

    def _blurbs(pictures: list[FactPicture]) -> None:
        batches.append(list(pictures))

    cache = WarmCache(circle=_Circle(answer=[_SHOWN]), blurbs=_blurbs, spawn=_sync)

    cache.ask(["The Shawshank Redemption"])

    assert batches == [[("Побег из Шоушенка", 1994, "movie")]]


def test_a_refused_circle_does_not_stop_the_queue_behind_it() -> None:
    """Один отказ - не конец прогрева: следующая плитка экрана греется как ни в чём."""
    asked: list[str] = []

    def _circle(query: str) -> list[Plan]:
        asked.append(query)
        if query == "Ludwig":
            raise ServerDownError("prowlarr_down")
        return [_PLAN]

    cache = _cache(_circle)

    cache.ask(["Ludwig", "Kin"])

    assert asked == ["Ludwig", "Kin"]


def test_a_refused_circle_of_a_live_card_reaches_the_caller() -> None:
    """Живому запросу отказ отдаётся, а не гасится: карточка отвечает 409, а не пустотой."""

    def _circle(_query: str) -> list[Plan]:
        raise ServerDownError("prowlarr_down")

    cache = _cache(_circle)

    with pytest.raises(ServerDownError):
        cache.take("Ludwig")


def test_an_open_card_does_not_queue_behind_a_background_circle_of_another_tile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Карточка ставила свой круг в срочную очередь и ждала, пока фон досчитает чужой."""
    monkeypatch.setattr("web.warm_cache.BUSY_WAIT", 2.0)
    circle = _Circle()
    held: list[Callable[[], None]] = []  # the only hand is busy with another tile's circle
    cache = _cache(circle, spawn=held.append)
    cache.hint("Interstellar")

    started = time.monotonic()
    taken = cache.take("Interstellar")

    assert (taken, circle.asked) == ([_PLAN], ["Interstellar"])
    assert time.monotonic() - started < 1.0
    for hand in held:
        hand()  # the hand comes back later and does not count the same circle again
    assert circle.asked == ["Interstellar"]


@pytest.mark.machine
def test_the_background_waits_while_a_live_request_holds_the_indexers() -> None:
    """Живое идёт вперёд очереди: пока карточка считает круг, фон не начинает своего."""
    hands: list[threading.Thread] = []
    live_started, release = threading.Event(), threading.Event()
    order: list[str] = []

    def _circle(query: str) -> list[Plan]:
        if query == "live":
            live_started.set()
            release.wait(5.0)
            order.append("live")
            return [_PLAN]
        order.append("warm")
        return [_PLAN]

    def _thread(job: Callable[[], None]) -> None:
        hand = threading.Thread(target=job, daemon=True)
        hands.append(hand)
        hand.start()

    cache = _cache(_circle, spawn=_thread)
    caller = threading.Thread(target=lambda: cache.take("live"), daemon=True)
    hands.append(caller)
    caller.start()
    assert live_started.wait(5.0)

    cache.ask(["Ludwig"])
    time.sleep(0.2)
    waited = list(order)
    release.set()
    for hand in hands:
        hand.join(5.0)

    assert waited == []
    assert order == ["live", "warm"]
    assert not [hand for hand in hands if hand.is_alive()]


@pytest.mark.machine
def test_a_live_request_waits_for_the_circle_the_background_is_already_counting() -> None:
    """🔴 Карточка с главной: фон уже считает круг плитки, живой не считает его второй раз."""
    hands: list[threading.Thread] = []
    started, release = threading.Event(), threading.Event()
    circle = _Circle()

    def _slow(query: str) -> list[Plan]:
        started.set()
        release.wait(5.0)
        return circle(query)

    def _thread(job: Callable[[], None]) -> None:
        hand = threading.Thread(target=job, daemon=True)
        hands.append(hand)
        hand.start()

    cache = _cache(_slow, spawn=_thread)
    cache.ask(["Interstellar"])
    assert started.wait(5.0)
    taken: list[list[Plan]] = []
    caller = threading.Thread(target=lambda: taken.append(cache.take("Interstellar")), daemon=True)
    hands.append(caller)
    caller.start()
    time.sleep(0.2)
    release.set()
    for hand in hands:
        hand.join(5.0)

    assert taken == [[_PLAN]]
    assert circle.asked == ["Interstellar"]
    assert not [hand for hand in hands if hand.is_alive()]


_TOLD: list[Told] = [("search", "Interstellar", 0.0, (), [RawResult("Interstellar 1080p", "h")])]


def _restarted(tmp_path: Path, circle: _Circle, spawn: Callable[[Callable[[], None]], None]) -> Any:
    replayed: list[str] = []

    def replay(query: str, told: list[Told]) -> list[Plan]:
        replayed.append(query)
        return [_PLAN] if told == _TOLD else []

    disk = CircleDisk(path=lambda: tmp_path / "circles.json")
    cache = WarmCache(circle, lambda _p: None, spawn, disk=disk, replay=replay)
    return cache, replayed


def test_after_a_restart_a_repeat_is_served_from_disk_and_refreshed_by_one_background_circle(
    tmp_path: Path,
) -> None:
    """🔴 Холодный процесс гнал круг заново, хотя тот же запрос считался минуту назад."""
    circle = _Circle(answer=ToldCircle([_PLAN], _TOLD))
    _restarted(tmp_path, circle, _sync)[0].take("Interstellar")
    held: list[Callable[[], None]] = []
    cache, replayed = _restarted(tmp_path, circle, held.append)

    assert cache.take("Interstellar ") == [_PLAN]
    pumps = [job for job in held if job == cache._pump]
    assert (circle.asked, replayed, len(pumps)) == (["Interstellar"], ["Interstellar "], 1)
    while held:
        held.pop(0)()
    assert cache.take("Interstellar") == [_PLAN]
    assert (circle.asked, replayed) == (["Interstellar", "Interstellar"], ["Interstellar "])


def test_a_cut_circle_is_not_written_to_disk(tmp_path: Path) -> None:
    circle = _Circle(answer=CutCircle([_PLAN], _TOLD))
    _restarted(tmp_path, circle, _sync)[0].take("Interstellar")

    cache, replayed = _restarted(tmp_path, circle, _sync)
    cache.take("Interstellar")

    assert (circle.asked, replayed) == (["Interstellar", "Interstellar"], [])


def test_a_screen_after_a_restart_is_warmed_from_disk_without_the_indexers(tmp_path: Path) -> None:
    """Плитки экрана после перезапуска гнали по кругу каждая, хотя круги лежали на диске."""
    circle = _Circle(answer=ToldCircle([_PLAN], _TOLD))
    _restarted(tmp_path, circle, _sync)[0].take("Interstellar")
    cache, replayed = _restarted(tmp_path, circle, _sync)

    assert cache.ask(["Interstellar"]) == 1
    assert (circle.asked, replayed) == (["Interstellar"], ["Interstellar"])
    assert cache.ready("Interstellar") == [_PLAN]
