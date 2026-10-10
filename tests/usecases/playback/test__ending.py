"""Зеркало конца картинки: готовый паспорт встаёт в список, поздний - за упаковкой, старт не ждёт.

Лента тут ручная: упаковка не поднимается, а перезаход виден списком ``restarts``. Сетки
настоящие (:func:`tests.usecases.playback.world.grid`): по ним меряется расхождение.
"""

from __future__ import annotations

import time
from concurrent.futures import Future
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, cast

import pytest

import torrcast.ports.journal.slot as slot
import torrcast.usecases.playback._show_state as _state
from tests.usecases.feed_pack.world import FakeClock
from tests.usecases.playback.world import grid
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.ports.journal.silent import Silent
from torrcast.usecases.playback._ending import PICTURE_CAP, _Ending
from torrcast.usecases.playback.ended_feed import EndedFeed
from torrcast.usecases.watch import Watch

#: Длительность контейнера: звук дольше картинки, как у «Отчаянных домохозяек» s3.
CONTAINER = 300.0
#: Конец картинки по хвосту файла.
PICTURE = 295.0


class _Marks(Silent):
    def __init__(self) -> None:
        self.rows: list[tuple[str, dict[str, object]]] = []

    def mark(self, name: str, **facts: object) -> None:
        self.rows.append((name, facts))

    def names(self) -> list[str]:
        return [name for name, _facts in self.rows]


@dataclass
class _Feed:
    """Лента без упаковки: что лежит на диске и куда перезашла упаковка."""

    grid: Grid
    door: int = 0
    on_disk: int = 0
    recoder: object = None
    vault: object = None
    settle: object = None
    packer: object = None
    played: float = 0.0
    restarts: list[int] = field(default_factory=list)

    def have(self, slot: int) -> bool:
        return slot < self.on_disk

    def restart(self, slot: int) -> None:
        self.restarts.append(slot)
        self.door = slot


@dataclass
class _Packer:
    """Живой прогон упаковки: откуда начат и докуда выложил."""

    first: int = 0
    edge: int = 0
    halted: bool = False
    code: int | None = None

    def poll(self) -> int | None:
        return self.code


@dataclass
class _Recoder:
    events: list[str] = field(default_factory=list)
    played: float = -1.0

    def stock(self, _stocked: object) -> None:
        self.events.append("stock")

    def start(self) -> None:
        self.events.append("start")

    def stop(self) -> None:
        self.events.append("stop")


@dataclass
class _Server:
    labels: list[set[int]] = field(default_factory=list)

    def relabel(self, warm_recodes: set[int]) -> None:
        self.labels.append(warm_recodes)


class _Receiver:
    next_cut: Any = None


@pytest.fixture
def marks(monkeypatch: pytest.MonkeyPatch) -> _Marks:
    spy = _Marks()
    monkeypatch.setattr(slot._slot, "_sink", spy)
    monkeypatch.setattr(_state, "CLOCK", FakeClock(), raising=False)
    return spy


def _passport(duration: float) -> Future[Media]:
    ahead: Future[Media] = Future()
    ahead.set_result(Media(duration, (AudioTrack(index=0, language="rus"),), "h264", 1080, 1920))
    return ahead


def _ending(ahead: Future[Media], feed: _Feed, **kw: Any) -> tuple[_Ending, dict[str, Any]]:
    watch = Watch(
        key="k",
        entry=Entry(title="серия", query="серия", magnet="magnet:?xt=1", dur=CONTAINER),
        every=0.0,
    )
    world: dict[str, Any] = {
        "watch": watch,
        "supply": SimpleNamespace(duration=CONTAINER),
        "old": _Recoder(),
        "new": _Recoder(),
        "warmer": SimpleNamespace(vault=SimpleNamespace(served={4, 5}), rival=None),
        "server": _Server(),
        "receiver": _Receiver(),
        "built": [],
    }

    def rebuild(*, grid: Grid, warm: bool = True) -> tuple[Any, Any]:
        world["built"].append(grid)
        world["warm"] = warm
        return world["new"], world["warmer"] if warm else None

    ending = _Ending(
        ahead,
        watch,
        world["supply"],
        lambda: (grid(watch.entry.dur), None),
        rebuild,
        cast(EndedFeed, feed),
        world["server"],
        world["receiver"],
        world["old"],
        None,
        12.0,
        **kw,
    )
    return ending, world


def test_a_shorter_picture_regrids_ahead_of_the_pack(marks: _Marks) -> None:
    """Конец картинки раньше контейнера: сетка, запись, раздача и упаковка встают по нему."""
    feed = _Feed(grid(CONTAINER), on_disk=3)
    ending, world = _ending(_passport(PICTURE), feed)

    ending()

    assert feed.grid.count == grid(PICTURE).count
    assert feed.grid.end(feed.grid.count - 1) == pytest.approx(PICTURE)
    assert world["watch"].entry.dur == PICTURE and world["supply"].duration == PICTURE
    assert world["built"] == [feed.grid]
    assert feed.restarts == [3] and feed.door == 0
    assert world["old"].events == ["stop"] and world["new"].events == ["stock", "start"]
    assert world["new"].played == 12.0 and feed.recoder is world["new"]
    assert feed.vault is world["warmer"].vault and world["server"].labels == [{4, 5}]
    assert world["receiver"].next_cut == feed.grid.after
    assert "сетка по картинке" in marks.names()


def test_the_same_end_leaves_the_show_alone(marks: _Marks) -> None:
    """Паспорт совпал с записью: перезахода нет, сетка та же."""
    old = grid(CONTAINER)
    feed = _Feed(old)
    ending, world = _ending(_passport(CONTAINER), feed)

    ending()

    assert feed.grid is old and feed.restarts == [] and world["built"] == []
    assert marks.names() == ["конец картинки"]


def test_the_playlist_does_not_wait_for_a_late_passport(marks: _Marks) -> None:
    """Хвост файла ещё читается: список уходит сразу, по контейнеру (стенд: +8 с к старту)."""
    feed = _Feed(grid(CONTAINER))
    ending, world = _ending(Future(), feed)

    began = time.monotonic()
    ending()

    assert time.monotonic() - began < 0.5
    assert feed.restarts == [] and world["watch"].entry.dur == CONTAINER
    assert marks.names() == ["конец картинки опоздал"]


def _late(feed: _Feed) -> tuple[_Ending, dict[str, Any], Future[Media]]:
    """Список ушёл без паспорта, прогрев отдан показу, потом паспорт дочитан."""
    ahead: Future[Media] = Future()
    ending, world = _ending(ahead, feed)
    world["running"] = SimpleNamespace(vault=SimpleNamespace(served={7}), rival=None)
    ending.warmer = cast(Any, world["running"])
    ending()
    assert ending.hand() is world["running"]
    ahead.set_result(_passport(PICTURE).result())
    return ending, world, ahead


def test_a_late_passport_waits_for_the_pack_to_reach_the_change(marks: _Marks) -> None:
    """Поздний паспорт: пока упаковка не дошла до расхождения, ни сетка, ни прогон не меняются."""
    old = grid(CONTAINER)
    feed = _Feed(old, on_disk=3, packer=_Packer(first=0, edge=5))
    ending, world, _ahead = _late(feed)

    ending.tick()

    assert feed.grid is old and feed.restarts == [] and world["built"] == []
    assert world["watch"].entry.dur == CONTAINER
    assert marks.names()[-1] == "сетка по картинке ждёт упаковку"


def test_a_late_passport_regrids_from_the_change_on_and_keeps_the_warm_up(marks: _Marks) -> None:
    """Упаковка у куска перед расхождением: прогон перезаходит с него, прогрев остаётся свой."""
    feed = _Feed(grid(CONTAINER), on_disk=3, packer=_Packer(first=0, edge=27))
    ending, world, _ahead = _late(feed)
    cut = 28

    ending.tick()

    assert feed.grid.count == grid(PICTURE).count
    assert feed.grid.end(feed.grid.count - 1) == pytest.approx(PICTURE)
    assert feed.restarts == [cut] and feed.door == 0
    assert world["warm"] is False and world["running"].rival is world["new"]
    assert feed.vault is None and world["server"].labels == []
    assert ending.warmer is world["running"]
    assert world["watch"].entry.dur == PICTURE and world["supply"].duration == PICTURE
    assert world["receiver"].next_cut == feed.grid.after
    assert marks.names()[-1] == "сетка по картинке"
    ending.tick()
    assert feed.restarts == [cut]


def test_a_late_passport_after_the_change_was_packed_is_refused(marks: _Marks) -> None:
    """Кусок расхождения уже лежит по старой сетке: место фильма за ним не меняется."""
    old = grid(CONTAINER)
    feed = _Feed(old, on_disk=29, packer=_Packer(first=0, edge=28))
    ending, world, _ahead = _late(feed)

    ending.tick()

    assert feed.grid is old and feed.restarts == [] and world["built"] == []
    assert world["watch"].entry.dur == CONTAINER
    assert marks.names()[-1] == "сетка по картинке не встала"


def test_a_late_passport_without_a_live_pack_swaps_the_grid_alone(marks: _Marks) -> None:
    """Прогон погашен паузой: сетка меняется сразу, а поднимет упаковку следующий запрос."""
    feed = _Feed(grid(CONTAINER), on_disk=3, packer=_Packer(edge=5, halted=True))
    ending, _world, _ahead = _late(feed)

    ending.tick()

    assert feed.grid.count == grid(PICTURE).count and feed.restarts == []


def test_a_late_passport_is_settled_once(marks: _Marks) -> None:
    feed = _Feed(grid(CONTAINER), packer=_Packer(edge=27))
    ending, world, ahead = _late(feed)

    ending._late(ahead)
    ending.tick()

    assert len(world["built"]) == 1 and feed.restarts == [28]


def test_an_unread_passport_keeps_the_container_grid(marks: _Marks) -> None:
    ahead: Future[Media] = Future()
    ahead.set_exception(InfraError("служба раздач молчит"))
    feed = _Feed(grid(CONTAINER))
    ending, _world = _ending(ahead, feed)

    ending()

    assert feed.restarts == [] and marks.names() == ["конец картинки не прочитан"]


@pytest.mark.parametrize(("door", "on_disk"), [(29, 29), (0, 30)])
def test_a_change_behind_the_pack_is_refused(marks: _Marks, door: int, on_disk: int) -> None:
    """Расхождение там, где упаковка уже прошла: куски на диске не меняют места фильма."""
    old = grid(CONTAINER)
    feed = _Feed(old, door=door, on_disk=on_disk)
    ending, world = _ending(_passport(PICTURE), feed)

    ending()

    assert feed.grid is old and feed.restarts == [] and world["built"] == []
    assert world["watch"].entry.dur == CONTAINER and world["supply"].duration == CONTAINER
    assert "сетка по картинке не встала" in marks.names()


def test_the_end_is_settled_once_per_show(marks: _Marks) -> None:
    """Список кусков просят много раз: ждать и пересобирать - только в первый."""
    feed = _Feed(grid(CONTAINER), on_disk=1)
    ending, world = _ending(_passport(PICTURE), feed)

    ending()
    ending()

    assert feed.restarts == [1] and len(world["built"]) == 1


def test_after_load_hands_over_the_warm_up_of_the_new_grid(marks: _Marks) -> None:
    """Браузер берёт список после LOAD: прогрев показа обязан быть уже на новой сетке."""
    feed = _Feed(grid(CONTAINER), on_disk=1)
    ending, world = _ending(_passport(PICTURE), feed)
    feed.settle = ending

    warmer = _Ending.after_load(cast(EndedFeed, feed), cast(Any, "прежний"))

    assert warmer is world["warmer"]


def test_after_load_does_not_wait_for_a_late_passport(marks: _Marks) -> None:
    """Вкладка браузера: LOAD взят, паспорта нет - прогрев идёт на нынешней сетке сразу."""
    feed = _Feed(grid(CONTAINER))
    ending, _world = _ending(Future(), feed)
    feed.settle = ending
    prior: Any = "прежний"
    ending.warmer = prior

    began = time.monotonic()
    warmer = _Ending.after_load(cast(EndedFeed, feed), prior)

    assert time.monotonic() - began < 0.5 and warmer is prior
    assert marks.names() == ["конец картинки опоздал"]


def test_after_load_without_an_ending_keeps_the_warm_up(marks: _Marks) -> None:
    feed = _Feed(grid(CONTAINER))
    prior: Any = object()
    assert _Ending.after_load(cast(EndedFeed, feed), prior) is prior


def test_the_passport_is_read_only_after_the_first_frame(marks: _Marks) -> None:
    """До картинки ни голова, ни хвост файла не читаются: заход упаковки рой не делит.

    Отрицательная проба: ``tick`` пускает паспорт без картинки - первый ``go`` до кадра.
    """
    shown, went = [False], []
    ending, _world = _ending(
        Future(), _Feed(grid(CONTAINER)), picture=lambda: shown[0], go=lambda: went.append(1)
    )

    ending.tick()
    assert went == [] and "паспорт пошёл" not in marks.names()
    shown[0] = True
    ending.tick()
    ending.tick()

    assert went == [1] and marks.names().count("паспорт пошёл") == 1


def test_an_unseen_picture_still_lets_the_passport_go_after_the_cap(marks: _Marks) -> None:
    """Картинку не заметили, а показ идёт: паспорт всё равно дочитывается, позже."""
    went: list[int] = []
    ending, _world = _ending(Future(), _Feed(grid(CONTAINER)), go=lambda: went.append(1))

    cast(FakeClock, _state.CLOCK).now += PICTURE_CAP - 1.0
    ending.tick()
    assert went == []
    cast(FakeClock, _state.CLOCK).now += 1.0
    ending.tick()

    assert went == [1]
