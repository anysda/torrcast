"""Лента показа снаружи: манифест, приговор источнику и подмена решений наследником."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

import torrcast.usecases.feed_pack.feed_segment as feed_segment
from tests.usecases.feed_pack.world import feed, grid, here, lay, packer, tract, vault
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.warm.segment_start import _Clock

if TYPE_CHECKING:
    from pathlib import Path


def test_the_manifest_promises_the_whole_film_in_bytes(tmp_path: Path) -> None:
    """Манифест уходит приёмнику байтами и обещает весь фильм.

    Иначе у показа нет ни таймлайна, ни перемотки: длительность приёмнику взять негде.
    """
    show = feed(tmp_path, grid=grid(60.0, 10.0))

    body = show.manifest()

    assert isinstance(body, bytes)
    assert body.decode("utf-8") == show.grid.manifest()
    assert show.duration == 60.0


def test_the_live_shelf_uses_the_selected_containers_name(tmp_path: Path) -> None:
    from torrcast.domain.segment_container import FMP4

    assert feed(tmp_path).piece_name(7) == "v7.ts"
    assert feed(tmp_path, container=FMP4).piece_name(7) == "v7.m4s"


def test_init_request_publishes_the_header_before_answering(tmp_path: Path) -> None:
    clock = tract()
    show = feed(tmp_path, wait=1.0)

    class _Run:
        def publish(self) -> None:
            (show.out / "init.mp4").write_bytes(b"init")

    show.packer = _Run()  # type: ignore[assignment]

    assert show.init() == show.out / "init.mp4"
    assert not clock.slept, "готовый заголовок отдаётся без ожидания"


def test_a_restart_overridden_by_an_heir_is_the_one_that_gets_called(tmp_path: Path) -> None:
    """Решение о перезапуске зовётся через объект: подмена наследником обязана доезжать.

    Стенды показа подменяют ровно этот метод, чтобы проверять учёт обрывов без ffmpeg.
    Позови решение модульную функцию напрямую - и подмена ставилась бы в никуда, а
    зеркало оставалось бы зелёным на поднявшемся по-настоящему ffmpeg.
    """
    asked: list[int] = []

    class _Noting(Feed):
        def restart(self, slot: int) -> None:
            asked.append(slot)

    show = _Noting(source="src", audio=0, out=tmp_path, grid=grid(), wait=0.0)

    assert show._steer(2) is True
    assert asked == [2], "перезапуск ушёл мимо наследника"


def test_the_drift_of_a_show_without_a_run_is_a_zero_and_not_a_guess(tmp_path: Path) -> None:
    """Упаковки нет - расхождения с манифестом не выдумываем."""
    show = feed(tmp_path)
    assert show.drift() == 0.0

    show.packer = packer(tmp_path, first=0)
    assert show.drift() == 0.0, "списка нарезки нет - расхождение всё равно ноль"


class _SwappingFeed(Feed):
    """Лента, у которой прогон исчезает ровно между двумя чтениями поля."""

    reads = 0

    def __getattribute__(self, name: str) -> object:
        if name == "packer":
            type(self).reads += 1
            if type(self).reads == 2:
                self.packer = None
        return super().__getattribute__(name)


def test_drift_survives_the_run_swapped_between_two_readings(tmp_path: Path) -> None:
    """Расхождение спрашивают у снимка прогона, даже если поле уже перепривязано."""
    _SwappingFeed.reads = 0
    show = feed(tmp_path, kind=_SwappingFeed)
    show.packer = packer(tmp_path, first=0)

    assert show.drift() == 0.0
    assert _SwappingFeed.reads == 1, "поле прогона читается один раз, снимком"


def test_halted_survives_the_run_swapped_between_two_readings(tmp_path: Path) -> None:
    """Состояние паузы спрашивают у снимка прогона, даже если поле уже перепривязано."""
    _SwappingFeed.reads = 0
    show = feed(tmp_path, kind=_SwappingFeed)
    show.packer = packer(tmp_path, first=0, halted=True)

    assert show.halted() is True
    assert _SwappingFeed.reads == 1, "поле прогона читается один раз, снимком"


def test_halt_survives_the_run_swapped_between_two_readings(tmp_path: Path) -> None:
    """Паузу передают снимку прогона, даже если поле уже перепривязано."""
    _SwappingFeed.reads = 0
    show = feed(tmp_path, kind=_SwappingFeed)
    live = packer(tmp_path, first=0)
    show.packer = live

    show.halt()

    assert live.halted is True
    assert _SwappingFeed.reads == 1, "поле прогона читается один раз, снимком"


def test_a_source_that_came_back_lifts_the_verdict_without_forgiving_nothing(
    tmp_path: Path,
) -> None:
    """Виноват источник - приговор снимается, обрывы забываются, а показ говорит почему."""
    show = feed(tmp_path)
    show.fatal = "упаковка оборвалась"
    show.crashes = 5

    show.stall("служба раздач перезапускается")

    assert show.trouble() == "" and show.crashes == 0
    assert show.offline == "служба раздач перезапускается"


def test_the_pause_is_asked_of_the_run_and_answered_by_it(tmp_path: Path) -> None:
    """Пауза на пульте гасит прогон; без прогона это не поломка, а тишина."""
    show = feed(tmp_path)
    show.halt()  # прогона нет - падать не на чем
    assert show.halted() is False

    show.packer = packer(tmp_path, first=0)
    show.halt()

    assert show.halted() is True and show.packer.stopped == "пауза на пульте"


def test_a_warmed_piece_handed_out_raises_the_packing_for_the_seam_behind_it(
    tmp_path: Path, tape: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Выдача прогретого - единственное место, где виден ход показа по прогретому.

    К упаковке такой запрос не обращается вовсе, поэтому за концом прогретого отрезка
    не оказывалось ничего: разбор ленты сеанса - 13.08 с потерянной плёнки на первом же
    месте за границей. Проба идёт через саму ленту: собери её без стыка, и подъём
    упаковки уехал бы в никуда при зелёном зеркале самого стыка.
    """
    tract(now=100.0, spawn=here)
    monkeypatch.setattr(feed_segment, "segment_start", lambda path: _Clock(50.0, movie=True))
    asked: list[int] = []

    class _Noting(Feed):
        def restart(self, slot: int) -> None:
            asked.append(slot)

    store = vault(tmp_path)
    show = feed(tmp_path, kind=_Noting, grid=grid(600.0, 10.0), vault=store)
    for slot in range(11):
        lay(store.dir, slot)

    assert show.segment(5) == store.dir / "v5.ts"
    assert asked == [11], "выдача прогретого прошла мимо стыка"
