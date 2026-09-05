"""The optional anime source narrows the catalog instead of breaking search."""

import importlib.util
import subprocess
import threading
from pathlib import Path
from typing import Any, NoReturn

import pytest

SPEC = importlib.util.spec_from_file_location(
    "anilibria_indexer", Path(__file__).parents[1] / "scripts/anilibria-indexer.py"
)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def _raise(error: BaseException) -> Any:
    """A fetch that only ever fails: the source is dead in the way the test names."""

    def fetch(*_args: str) -> NoReturn:
        raise error

    return fetch


def test_dead_primary_uses_the_alternative() -> None:
    calls: list[str] = []

    def answer(origin: str, path: str, _seconds: float = 0.0) -> Any:
        calls.append(origin)
        if origin == adapter.ORIGINS[0]:
            raise OSError("silent")
        if "/search/" in path:
            return [{"id": 7, "name": {"english": "Sonny Boy"}}]
        return [{"label": "Sonny Boy 1080p", "magnet": "magnet:?xt=urn:btih:abc"}]

    assert adapter.search("Sonny Boy", answer)[0]["title"] == "Sonny Boy 1080p"
    assert set(calls[:2]) == set(adapter.ORIGINS), (
        f"both mirrors are asked, in whichever order they come back: {calls[:2]}"
    )


def test_all_dead_sources_are_an_empty_result() -> None:
    assert adapter.search("Kaiba", _raise(OSError())) == []


def test_hung_sources_are_an_empty_result_and_not_a_dropped_connection() -> None:
    """A stall is how this source usually dies, and it does not arrive as OSError:
    `subprocess.run` raises its own TimeoutExpired, which descends from SubprocessError.
    Uncaught it leaves the handler as a dropped connection, and Prowlarr answers a dropped
    connection with a ban ladder - the step for a source that does not answer is a whole
    day, so one stall would cost the whole search instead of narrowing the catalog."""
    assert adapter.search("Kaiba", _raise(subprocess.TimeoutExpired("curl", 4.0))) == []


def test_a_release_that_hangs_on_details_only_drops_itself() -> None:
    """The details of a release are asked for after the listing answered, so a stall there
    reaches a second catch - and it too owes the caller rows, not a broken connection."""

    def answer(_origin: str, path: str, _seconds: float = 0.0) -> Any:
        if "/search/" in path:
            return [{"id": 7, "name": {"english": "Kaiba"}}]
        raise subprocess.TimeoutExpired("curl", 4.0)

    assert adapter.search("Kaiba", answer) == []


def test_fuzzy_search_cannot_substitute_an_unrelated_release() -> None:
    def answer(_origin: str, path: str, _seconds: float = 0.0) -> Any:
        if "/search/" in path:
            return [
                {"id": 1, "name": {"english": "Kono Healer, Mendokusai"}},
                {"id": 2, "name": {"english": "Serial Experiments Lain"}},
            ]
        release = path.rsplit("/", 1)[-1]
        return [{"label": f"release {release}", "magnet": f"magnet:?xt=urn:btih:{release}"}]

    found = adapter.search("Serial Experiments Lain", answer)
    assert [row["title"] for row in found] == ["release 2"]


def test_empty_query_does_not_accept_the_whole_catalog() -> None:
    def answer(*_args: str) -> Any:
        return [{"id": 1, "name": {"english": "Kaiba"}}]

    assert adapter.search("", answer) == []


def test_a_release_whose_details_stall_once_is_asked_again() -> None:
    """A stalled detail call is usually the source hiccupping, not a release that is gone.

    Without the second ask the release contributes nothing and vanishes from the catalog
    without a word - measured on the live stand, six releases out of forty went that way.
    """
    asked: list[str] = []

    def answer(_origin: str, path: str, _seconds: float = 0.0) -> Any:
        if "/search/" in path:
            return [{"id": 7, "name": {"english": "Kaiba"}}]
        asked.append(path)
        if len(asked) == 1:
            raise subprocess.TimeoutExpired("curl", 1.2)
        return [{"label": "Kaiba 1080p", "magnet": "magnet:?xt=urn:btih:abc"}]

    found = adapter.search("Kaiba", answer)
    assert [row["title"] for row in found] == ["Kaiba 1080p"], "the release must survive a hiccup"
    assert len(asked) == 2, "a stalled detail call is asked once more"


def test_details_carry_a_deadline_short_enough_to_ask_twice() -> None:
    """The second ask is only affordable because the details wait less than the listing."""
    deadlines: list[float] = []

    def answer(_origin: str, path: str, seconds: float = 0.0) -> Any:
        if "/search/" in path:
            return [{"id": 7, "name": {"english": "Kaiba"}}]
        deadlines.append(seconds)
        return [{"label": "Kaiba 1080p", "magnet": "magnet:?xt=urn:btih:abc"}]

    adapter.search("Kaiba", answer)
    assert deadlines, "the details were asked at all"
    spent = deadlines[0] * adapter.DETAIL_TRIES
    assert spent < adapter.TIMEOUT, f"two asks cost {spent} s, one old ask cost {adapter.TIMEOUT} s"


#: Сколько ждёт защёлка, прежде чем признать соседа не пришедшим.
#:
#: 🔴 Это НЕ порог замера, а цена независания: на счастливом пути защёлка снимается
#: событием и не стоит ни секунды, а срок платится ровно тогда, когда зеркала пошли по
#: очереди, - и платится он один раз, ради красной строки вместо вечного ожидания. Обе
#: меры ниже - состояния событий, а не длительности, поэтому нагрузка машины двигать их
#: не может: чтобы срок сработал ложно, заглушке в памяти пришлось бы считаться двадцать
#: секунд. Старый порог был 0.5 с при работе на 0.3 с (TC-1053), и его двигала уже
#: обычная волна: 5 красных прогонов из 50 под нагрузкой в 8 занятых ядер.
_STUCK_SECONDS = 20.0


def _settle() -> None:
    """Дождаться зеркала, ответ которого уже не нужен: в жизни его никто не ждёт.

    Счастливый путь второе зеркало НЕ ждёт - в этом и правка. Но проба, оставившая живой
    поток, покрасит соседнюю ложно, поэтому здесь его дожидаются явно, уже после замера.
    """
    for thread in threading.enumerate():
        if thread.name.startswith("anilibria-origin"):
            thread.join(_STUCK_SECONDS)


@pytest.mark.machine
def test_both_mirrors_are_asked_at_once_not_one_after_the_other() -> None:
    """Первое зеркало отвечает 403 на всё, и его отказ не смеет стоить второму ожидания.

    Одновременность доказывается ПОРЯДКОМ событий: отказ первого зеркала здесь ждёт
    защёлку, которую ставит ВХОД во второе. Очередь такую защёлку не поставила бы никогда -
    на момент отказа первого второго зеркала в ней ещё нет вовсе, и ожидание кончилось бы
    сроком. Замер на стенде до правки: 0.68 с на отказ первого плюс ответ второго.
    """
    asked_second = threading.Event()
    together: list[bool] = []

    def answer(origin: str, path: str, _seconds: float = 0.0) -> Any:
        if "/search/" not in path:
            return [{"label": "Sonny Boy 1080p", "magnet": "magnet:?xt=urn:btih:abc"}]
        if origin == adapter.ORIGINS[0]:
            together.append(asked_second.wait(_STUCK_SECONDS))
            raise OSError("403")
        asked_second.set()
        return [{"id": 7, "name": {"english": "Sonny Boy"}}]

    try:
        rows = adapter.search("Sonny Boy", answer)
        assert together and together[0], (
            "к отказу первого зеркала второе ещё не было спрошено - значит, шли по очереди"
        )
        assert rows[0]["title"] == "Sonny Boy 1080p"
    finally:
        asked_second.set()
        _settle()


@pytest.mark.machine
def test_a_healthy_first_mirror_wins_and_is_not_waited_out_by_the_slow_one() -> None:
    """Порядок зеркал остался ПРЕДПОЧТЕНИЕМ: каталог читаем прежний, но не ждём второе.

    🔴 TC-1053. Мера - ПОРЯДОК событий, а не стенные часы: под четырьмя воркерами xdist
    время тесту не принадлежит, и «уложились в 0.5 с» краснело по жребию. Медленное
    зеркало держит здесь не ``sleep``, а защёлка, и утверждений ровно два:

    * здоровое зеркало отвечает, когда медленное УЖЕ спрошено, - значит, поехали разом;
    * ``search`` возвращается, когда медленное ЕЩЁ не ответило, - значит, его не ждали.

    Оба - про состояние события в известный момент, и оба одинаково читаются что на
    пустой машине, что на занятой.
    """
    asked_slow = threading.Event()
    let_slow_go = threading.Event()
    slow_answered = threading.Event()
    together: list[bool] = []

    def answer(origin: str, path: str, _seconds: float = 0.0) -> Any:
        if origin == adapter.ORIGINS[1]:
            asked_slow.set()
            let_slow_go.wait(_STUCK_SECONDS)
            slow_answered.set()
            return [{"id": 9, "name": {"english": "Sonny Boy"}}] if "/search/" in path else []
        if "/search/" in path:
            together.append(asked_slow.wait(_STUCK_SECONDS))
            return [{"id": 7, "name": {"english": "Sonny Boy"}}]
        return [{"label": "Sonny Boy 1080p", "magnet": "magnet:?xt=urn:btih:abc"}]

    try:
        rows = adapter.search("Sonny Boy", answer)
        assert together and together[0], (
            "к ответу первого зеркала второе ещё не было спрошено - значит, шли по очереди"
        )
        assert not slow_answered.is_set(), "ответ первого зеркала дождался молчащего второго"
        assert rows[0]["title"] == "Sonny Boy 1080p"
    finally:
        let_slow_go.set()
        asked_slow.set()
        _settle()
