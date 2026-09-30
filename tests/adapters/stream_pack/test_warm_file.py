"""Проверяет фоновый прогрев файла: порядок трёх дел и размер головы по контейнеру."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Any

import pytest

from torrcast.adapters.stream_pack.warm_file import warm_file
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.frames.mkv.ids import CUES_CHUNK
from torrcast.domain.warm_open import HEAD_OPEN, HEAD_WARM

#: Замер начала ленты в ряду прогретых кусков: его место в порядке и есть договор.
MEASURED = (-1, -1)
#: Где индекс mkv у подставного файла.
CUES = 4 << 30


@dataclass
class Watch:
    """Наблюдатель за прогревом: карта под рукой, а прогретые куски - списком.

    Голову греет :func:`pull_head`, место позиции - сам :func:`warm_file`, но работа у них
    одна, поэтому наблюдатель один: ``warm`` уезжает в оба места договором.
    """

    keys: FilmKeys | None
    asked: list[tuple[int, int]] = field(default_factory=list)

    def warm(self, url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        self.asked.append((offset, upto))
        return 0

    def origin_of(self, url: str) -> float:
        self.asked.append(MEASURED)
        return 0.0

    def cues_of(self, url: str, alive: Any) -> int | None:
        return CUES

    def keys_of(self, url: str) -> FilmKeys:
        if self.keys is None:
            raise OSError("карта не снялась")
        return self.keys

    def wait(self, count: int) -> None:
        """Дождаться, пока фоновый прогрев отчитается о нужном числе кусков."""
        for _ in range(300):
            if len(self.asked) >= count:
                return
            time.sleep(0.01)


@pytest.mark.machine
def test_from_the_start_only_the_head_is_warmed() -> None:
    """С нуля греется начало, и только оно: место позиции и есть начало."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mp4"))
    warm_file(
        "http://торрент/поток",
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    watch.wait(2)
    time.sleep(0.1)
    assert watch.asked == [(0, HEAD_WARM), MEASURED]


@pytest.mark.machine
def test_the_middle_warms_the_header_and_the_place_of_the_position() -> None:
    """Продолжение с середины греет заголовок и место позиции, а не 32 МБ чужого начала.

    Смещение берётся из карты: доля «позиция от длительности на размер файла» промахнулась
    бы на четверть фильма.
    """
    watch = Watch(FilmKeys(600.0, [0.0, 100.0, 200.0], [0, 90 << 20, 500 << 20], "mp4"))
    warm_file(
        "http://торрент/поток",
        at=240.0,
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    watch.wait(3)
    assert watch.asked == [(0, HEAD_OPEN["mp4"]), MEASURED, (500 << 20, HEAD_WARM)]


@pytest.mark.machine
def test_the_head_is_sized_by_the_container_of_the_map() -> None:
    """У mkv головы мало, у mp4 там ``moov``: греть их поровну - отнимать полосу у показа."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mkv"))
    warm_file(
        "http://торрент/поток",
        at=240.0,
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    watch.wait(2)
    assert watch.asked[0] == (0, HEAD_OPEN["mkv"])


@pytest.mark.machine
def test_an_old_map_takes_the_container_from_the_name_of_the_file() -> None:
    """Карта из кэша прошлой версии контейнера не знает - его называет имя файла раздачи."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], ""))
    warm_file(
        "http://торрент/поток?link=hash&index=1",
        at=240.0,
        name="Moana.2.2024.mkv",
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    watch.wait(2)
    assert watch.asked[0] == (0, HEAD_OPEN["mkv"])


@pytest.mark.machine
def test_a_map_that_did_not_come_still_warms_the_head() -> None:
    """Не вышло с картой - не беда: показ сделает то же самое сам, просто на своём времени."""
    watch = Watch(None)
    warm_file(
        "http://торрент/поток",
        at=240.0,
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    watch.wait(1)
    time.sleep(0.1)
    assert watch.asked == [(0, HEAD_WARM), MEASURED], "без карты греть место позиции нечем"


@pytest.mark.machine
def test_a_release_the_show_gave_up_on_is_not_warmed_further() -> None:
    """Отвергнутый релиз дотягивать нельзя: он отъедает полосу у выбранного."""
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], "mp4"))
    warm_file(
        "http://торрент/поток",
        at=240.0,
        alive=lambda: False,
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    time.sleep(0.2)
    assert watch.asked == [], "прогрев пошёл по релизу, от которого показ уже отказался"


@pytest.mark.machine
def test_the_returned_event_marks_a_map_taken_or_refused() -> None:
    """Событие встаёт, когда карта снята или отказана: по нему отбор в срок ждёт сетку."""
    for keys in (FilmKeys(600.0, [0.0], [0], "mp4"), None):
        watch = Watch(keys)
        mapped = warm_file(
            "http://торрент/поток",
            keys_of=watch.keys_of,
            warm=watch.warm,
            origin_of=watch.origin_of,
            cues_of=watch.cues_of,
        )
        assert mapped.wait(3.0), "карта кончилась, а событие не встало"


@pytest.mark.machine
@pytest.mark.parametrize(("name", "waits"), [("серия.avi", False), ("серия.mkv", True), ("", True)])
def test_a_file_no_map_is_read_from_does_not_hold_the_pick(name: str, waits: bool) -> None:
    """AVI карты не даёт: отбор не ждёт холодную голову ради её отказа, разбор идёт сам.

    Положительный контроль - mkv и безымянный файл: их карту отбор ждёт, пока она читается.
    """
    reading, release = threading.Event(), threading.Event()

    def keys_of(url: str) -> FilmKeys:
        reading.set()
        release.wait(3.0)
        raise OSError("это не mkv и не mp4")

    watch = Watch(None)
    mapped = warm_file(
        "http://торрент/поток",
        name=name,
        keys_of=keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    assert reading.wait(3.0), "разбор карты не пошёл"
    assert mapped.is_set() is not waits
    release.set()
    assert mapped.wait(3.0)


@pytest.mark.machine
def test_done_rises_after_the_place_of_the_position_even_when_it_fails() -> None:
    """Прогретой запись отмечают по ``done``: он ждёт конца всей цепочки, а не карты."""
    watch = Watch(FilmKeys(6000.0, [0.0, 3000.0], [0, 900 << 20], "mkv"))
    done, at_place, let_go = threading.Event(), threading.Event(), threading.Event()

    def warm(url: str, offset: int, upto: int = 0, alive: Any = None) -> int:
        watch.warm(url, offset, upto, alive)
        if offset:
            at_place.set()
            let_go.wait(3)
            raise OSError("рой молчит")
        return 0

    warm_file(
        "http://торрент/поток",
        at=3000.0,
        keys_of=watch.keys_of,
        warm=warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
        done=done,
    )

    assert at_place.wait(3)
    assert not done.wait(0.2), "встало до конца прогрева места закладки"
    let_go.set()
    assert done.wait(3), "отказ роя тоже конец цепочки"


@pytest.mark.machine
@pytest.mark.parametrize(("kind", "warms"), [("mkv", True), ("mp4", False)])
def test_the_middle_of_an_mkv_warms_its_cues_after_the_header(kind: str, warms: bool) -> None:
    """ffmpeg с ``-ss`` читает индекс mkv вторым; карта из кэша его не читает.

    Холодный индекс при прогретой закладке стоил кадру 7.4 с ожидания куска хвоста.
    Положительный контроль - mp4: у него индекс в голове, лишнего чтения быть не должно.
    """
    watch = Watch(FilmKeys(600.0, [0.0, 200.0], [0, 500 << 20], kind))
    warm_file(
        "http://торрент/поток",
        at=240.0,
        keys_of=watch.keys_of,
        warm=watch.warm,
        origin_of=watch.origin_of,
        cues_of=watch.cues_of,
    )
    watch.wait(4 if warms else 3)
    time.sleep(0.1)
    cues = [(CUES, CUES_CHUNK)] if warms else []
    assert watch.asked == [(0, HEAD_OPEN[kind]), *cues, MEASURED, (500 << 20, HEAD_WARM)]
