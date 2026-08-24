"""Переход с прогретого на живую упаковку: поднять её до того, как прогретое кончится."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from tests.usecases.feed_pack.world import (
    FakeProc,
    feed,
    grid,
    here,
    lay,
    packer,
    signals,
    tract,
    vault,
)
from torrcast.usecases.feed_pack.feed_seam import _seam

if TYPE_CHECKING:
    from pathlib import Path

    from tests.fakes.journal import Tape

#: Сетка замера: сто минут по десять секунд - лестница длиннее любой выдержки стыка.
LONG = 600.0


def _warmed(tmp_path: Path, upto: int, **parts: Any) -> Any:
    """Показ, у которого прогреты места ``0..upto``, а дальше плёнки нет ни у кого."""
    store = vault(tmp_path)
    show = feed(tmp_path, grid=grid(parts.pop("length", LONG), 10.0), vault=store, **parts)
    for slot in range(upto + 1):
        lay(store.dir, slot)
    return show


def test_the_packing_is_raised_before_the_warmed_stretch_runs_out(
    tmp_path: Path, tape: Tape
) -> None:
    """Прогретого впереди осталось ровно на выдержку - упаковка идёт за его конец.

    Разбор ленты сеанса: двадцать мест подряд ушли зрителю из прогретого, запас показа
    все эти секунды стоял мёртво на конце прогретого, а на первом месте за границей
    показ встал - два ``buffering``, три ``freeze``, 13.08 с потерянной плёнки.
    """
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)

    _seam(show, 5, asked.append)  # задел 110.0 - 50.0 = 60.0 с, ровно выдержка

    assert asked == [11], "стык не поднял упаковку за концом прогретого"
    assert show.restarted == 100.0, "подъём не отмечен часами: соседний запрос поднимет второй"
    assert not show.lock.locked(), "замок ленты остался закрытым после подъёма"


def test_a_long_warmed_stretch_ahead_costs_the_packing_nothing(tmp_path: Path, tape: Tape) -> None:
    """Прогретого впереди много - до прогона дело не доходит вовсе, и это вся его цена."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)

    _seam(show, 4, asked.append)  # задел 110.0 - 40.0 = 70.0 с, длиннее выдержки

    assert asked == [] and show.restarted == 0.0


def test_a_run_already_heading_for_the_seam_is_not_doubled(tmp_path: Path, tape: Tape) -> None:
    """Прогон подняли на этот же стык - второго ffmpeg в то же место не надо.

    ⚠️ Только что поднятый прогон не выложил ещё ничего. Прочитай стык это как
    отставание, и он поднимал бы вторую упаковку в то же место каждые две секунды.
    """
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)
    show.packer = packer(tmp_path, first=11, out=show.out)

    _seam(show, 5, asked.append)

    assert asked == [] and show.packer.edge == 10, "прогон, который ничего не выложил"


def test_a_run_working_far_from_the_seam_does_not_count_as_cover(
    tmp_path: Path, tape: Tape
) -> None:
    """Живой прогон в другом месте фильма стыка не обеспечивает: за концом всё равно пусто."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)
    show.packer = packer(tmp_path, first=0, edge=1, out=show.out)

    _seam(show, 5, asked.append)

    assert asked == [11]


def test_warmed_to_the_very_end_of_the_film_has_no_seam_at_all(tmp_path: Path, tape: Tape) -> None:
    """Прогретое доходит до конца фильма - паковать за ним нечего и не за чем."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 5, length=60.0)

    _seam(show, 0, asked.append)

    assert asked == []


def test_a_show_without_warmed_pieces_or_after_the_end_stays_out_of_it(
    tmp_path: Path, tape: Tape
) -> None:
    """Без прогретого стыка нет, а после конца показа поднимать ffmpeg некуда."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    bare = feed(tmp_path, grid=grid(LONG, 10.0))

    _seam(bare, 5, asked.append)
    assert asked == []

    show = _warmed(tmp_path, 10)
    show.fatal = "показ окончен"
    _seam(show, 5, asked.append)
    assert asked == []


def test_the_seam_does_not_push_a_packing_it_has_just_raised(tmp_path: Path, tape: Tape) -> None:
    """Куски приёмник просит пачкой - защита «не толкаемся» тут та же, что у запроса."""
    fake = tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)
    show.restarted = 99.0

    _seam(show, 5, asked.append)
    assert asked == [], "второй запрос той же пачки поднял вторую упаковку"

    fake.now = 103.0
    _seam(show, 5, asked.append)
    assert asked == [11]


def test_a_busy_lock_leaves_the_seam_to_the_neighbour(tmp_path: Path, tape: Tape) -> None:
    """Занятый замок значит «решение уже принимают»: вставать за ним в очередь нельзя."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)
    show.lock.acquire()

    _seam(show, 5, asked.append)

    assert asked == []


def test_the_raise_leaves_the_answer_to_the_receiver_alone(tmp_path: Path, tape: Tape) -> None:
    """Внутри подъёма лежит пробный прогон до минуты, а тут стоит поток с готовым куском.

    Поэтому подъём уходит в сторону вместе с замком и отпускает его сам.
    """
    work: list[Any] = []
    tract(now=100.0, spawn=work.append)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)

    _seam(show, 5, asked.append)

    assert asked == [] and show.lock.locked(), "подъём пошёл прямо в ответе приёмнику"
    work[0]()
    assert asked == [11] and not show.lock.locked()


def test_a_spawn_failure_does_not_lock_the_seam_forever(tmp_path: Path, tape: Tape) -> None:
    """Неподнятый поток не может навсегда отнять у стыка право поднять упаковку."""

    def broken(_work: object) -> None:
        raise RuntimeError("поток не поднялся")

    tract(now=100.0, spawn=broken)
    asked: list[int] = []
    show = _warmed(tmp_path, 10)

    with pytest.raises(RuntimeError, match="поток не поднялся"):
        _seam(show, 5, asked.append)
    tract(now=110.0, spawn=here)
    _seam(show, 5, asked.append)

    assert asked == [11], "сбой подъёма навсегда занял замок стыка"


def test_a_show_ended_mid_raise_takes_the_run_with_it(tmp_path: Path, tape: Tape) -> None:
    """Показ мог кончиться, пока прогон поднимали: поднятый следом читал бы в снесённый каталог."""
    work: list[Any] = []
    tract(now=100.0, spawn=work.append)
    show = _warmed(tmp_path, 10)

    _seam(show, 5, lambda slot: None)
    show.fatal = "показ окончен"
    show.packer = packer(tmp_path, first=11, out=show.out, proc=FakeProc())
    work[0]()

    assert signals(show.packer) == ["terminate"] and not show.lock.locked()
