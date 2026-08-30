"""Уборка по часам показа: сдать успевшее, поднять оборванное, вымести пройденное."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.usecases.feed_pack.world import (
    FakeProc,
    feed,
    grid,
    here,
    lay,
    packer,
    tract,
    vault,
)
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.feed_pack.feed_sweep import _lift, _prune, _sweep

if TYPE_CHECKING:
    from pathlib import Path


def nobody(_slot: int) -> None:
    """Перезапуск, которого проба не ждёт: она меряет соседнюю ступень уборки."""


def test_the_publish_is_called_by_the_clock_even_when_nobody_asks_for_a_piece(
    tmp_path: Path,
) -> None:
    """Пока показ берёт куски с диска, к упаковке никто не идёт, а ffmpeg пишет в tmpfs.

    Замер: 897 МБ несданного за 14 минут показа, рост без предела и без единой строки.
    """
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)

    _sweep(show, nobody)

    assert (show.out / "v0.ts").exists() and show.packer.edge == 0


def test_a_halted_or_missing_run_is_left_alone(tmp_path: Path) -> None:
    """Погашенную упаковку часы не поднимают: она встала намеренно."""
    show = feed(tmp_path)
    _sweep(show, nobody)  # прогона нет - падать не на чем

    show.packer = packer(tmp_path, first=0, out=show.out, halted=True)
    lay(show.packer.run, 0)
    lay(show.packer.run, 1)

    _sweep(show, nobody)

    assert list(show.out.glob("v*.ts")) == []


def test_unclaimed_pieces_over_the_ceiling_put_the_run_out_with_one_honest_line(
    tmp_path: Path, journal: Path
) -> None:
    """Куски, которых никто не забирает, стоят памяти и не дают приёмнику ничего."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append, pending_cap=1_000_000)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0, size=2_000_000)
    lay(show.packer.run, 1, size=2_000_000)
    lay(show.packer.run, 2, size=2_000_000)

    _sweep(show, nobody)

    assert show.packer.halted is True
    assert said == [phrase("feed.pending_too_big", mb="2")]


def test_unclaimed_pieces_under_the_ceiling_never_stop_a_working_run(
    tmp_path: Path,
) -> None:
    """Порог отделяет поломку от плотной работы, а не спорит с ней."""
    said: list[str] = []
    show = feed(tmp_path, log=said.append, pending_cap=1_000_000)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 0, size=900)
    lay(show.packer.run, 1, size=900)

    _sweep(show, nobody)

    assert show.packer.halted is False and said == []


def test_the_window_behind_the_show_is_the_free_seek_back(tmp_path: Path) -> None:
    """Позади показа держим окно ``keep``: глубже - уже перемотка, она перепакует поток."""
    show = feed(tmp_path, grid=grid(600.0, 10.0), keep=20.0)
    for slot in range(0, 12):
        lay(show.out, slot)

    _prune(show, played=100.0)

    assert sorted(int(p.stem[1:]) for p in show.out.glob("v*.ts")) == list(range(8, 12))


def test_the_leftovers_of_the_previous_place_of_the_show_are_swept_too(
    tmp_path: Path,
) -> None:
    """После отката назад впереди лежат места, до которых показ может уже и не дойти."""
    show = feed(tmp_path, grid=grid(600.0, 10.0), keep=600.0, ahead=2)
    show.packer = packer(tmp_path, first=0, edge=3, out=show.out)
    for slot in (0, 3, 5, 6, 40):
        lay(show.out, slot)

    _prune(show, played=5.0)

    assert sorted(int(p.stem[1:]) for p in show.out.glob("v*.ts")) == [0, 3, 5]


def test_without_a_run_nothing_ahead_is_touched(tmp_path: Path) -> None:
    """Прогона нет - край неизвестен, а гадать тут дороже, чем подождать."""
    show = feed(tmp_path, grid=grid(600.0, 10.0), keep=600.0)
    for slot in (0, 40):
        lay(show.out, slot)

    _prune(show, played=5.0)

    assert sorted(int(p.stem[1:]) for p in show.out.glob("v*.ts")) == [0, 40]


def test_a_torn_run_is_picked_up_by_the_clock_while_the_shelf_is_still_full(
    tmp_path: Path,
) -> None:
    """🔴 TC-725. Труп прогона обязан находиться по часам, а не по пустой полке.

    Живой замер: служба раздач упала на 17-й минуте показа, полка была полна - и
    разбирательство началось только через 31 с, когда запас впереди сошёл со 115 с
    до 13 с. Тут полка полна нарочно: за куском никто не придёт, и найти обрыв
    больше некому.
    """
    tract(now=100.0, spawn=here)
    said: list[str] = []
    asked: list[int] = []
    show = feed(tmp_path, log=said.append)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=1))
    for slot in range(0, 6):
        lay(show.out, slot)

    _sweep(show, asked.append)

    assert asked == [3], "оборванный прогон не подняли с места за краем"
    assert show.crashes == 1 and show.restarted == 100.0
    marker = "\x00"
    tail = phrase("feed.retrying", what=marker, attempt=1).split(marker)[1]
    assert said and said[0].endswith(tail)


def test_a_spawn_failure_does_not_silence_the_next_attempt(tmp_path: Path) -> None:
    """Неподнятый поток не может навсегда отнять у часов право чинить ленту."""

    def broken(_work: object) -> None:
        raise RuntimeError("поток не поднялся")

    tract(now=100.0, spawn=broken)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=1))

    with pytest.raises(RuntimeError, match="поток не поднялся"):
        _sweep(show, asked.append)
    tract(now=110.0, spawn=here)
    _sweep(show, asked.append)

    assert asked == [3], "сбой подъёма навсегда занял замок починки"


def test_a_living_run_is_never_restarted_by_the_clock(tmp_path: Path) -> None:
    """Прогон жив - паковать дальше ему никто не мешает, и трогать его незачем."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out)

    _sweep(show, asked.append)

    assert asked == [] and show.crashes == 0


def test_a_run_that_read_the_input_to_the_end_is_the_end_of_the_film(tmp_path: Path) -> None:
    """Дочитанный вход - это конец фильма, а не обрыв: поднимать нечего."""
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path, grid=grid(60.0, 10.0))
    show.packer = packer(tmp_path, first=0, edge=5, out=show.out, proc=FakeProc(code=0), whole=True)

    _sweep(show, asked.append)

    assert show.packer.finished() is True and asked == []


def test_the_clock_does_not_push_a_run_it_has_just_restarted(tmp_path: Path) -> None:
    """Часы идут вдвое чаще защиты «не толкаемся»: второй круг обязан промолчать."""
    fake = tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=1))

    _sweep(show, asked.append)
    fake.now = 101.0
    show.packer = packer(tmp_path, first=3, edge=4, out=show.out, proc=FakeProc(code=1))
    _sweep(show, asked.append)

    assert asked == [3], "сосед по часам толкнул упаковку внутри защиты"


def test_a_show_that_gave_up_for_good_is_buried_by_the_holder_and_not_by_the_sweep(
    tmp_path: Path,
) -> None:
    """Обрывы подряд без прогретого - приговор, и выносит его держатель показа."""
    fake = tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path, limit=1)
    for _attempt in range(0, 3):
        # Прогон, умерший на открытии входа: край ниже начала - выложить он не успел
        # ничего, и «источник снова читается» про такой прогон сказать нельзя.
        show.packer = packer(tmp_path, first=3, edge=2, out=show.out, proc=FakeProc(code=1))
        _sweep(show, asked.append)
        fake.now += 10.0

    assert asked == [3] and show.fatal, "приговор не вынесен или уборка продолжила толкать"


def test_the_clock_gives_the_first_word_about_a_tear_and_then_steps_aside(
    tmp_path: Path,
) -> None:
    """🔴 TC-725. Часам показа принадлежит ПЕРВАЯ весть, а не всё разбирательство.

    Идут они вчетверо чаще, чем приёмник просит куски. Оставь им и повторы - и весь счёт
    обрывов сгорел бы за секунды, а пятисекундная перезагрузка соседа стала бы
    приговором показу. Дальше обрыв ведёт запрос сегмента: у него на это есть выдержка.
    """
    fake = tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path, limit=1, vault=vault(tmp_path))
    for _attempt in range(0, 3):
        show.packer = packer(tmp_path, first=3, edge=2, out=show.out, proc=FakeProc(code=1))
        _sweep(show, asked.append)
        fake.now += 10.0

    # Два подъёма - это ровно путь до вести «источник лежит» (:attr:`limit` = 1), а не
    # три круга часов: как только показ это узнал, часы замолкают.
    assert asked == [3, 3], "часы забрали себе всё разбирательство, а не первую весть"
    assert not show.fatal and show.offline, "показ похоронен, хотя фильм лежит на диске"


def test_the_clock_lifts_a_provisional_verdict_the_receiver_can_never_ask_about(
    tmp_path: Path,
) -> None:
    """🔴 TC-725. Приёмник, упёршийся в дыру, просит ИМЕННО приговорённое место.

    Такой запрос отвечается молчанием, не заглядывая в прогон, - то есть единственный,
    кто мог бы снять приговор, до пересмотра не доходит. Живой замер: служба убита на
    70-й минуте, вернулась через пять секунд, а показ встал насмерть на 4234-й секунде.
    Поэтому пересмотр висит на часах показа, которым приёмник не указ.
    """
    tract(now=100.0, spawn=here)
    show = feed(tmp_path)
    show.packer = packer(tmp_path, first=0, edge=4, out=show.out)
    lay(show.packer.run, 5)
    show.skipped = {2, 7}
    show.doubted = {7}

    _sweep(show, nobody)

    assert show.skipped == {2}, "условный приговор пережил возврат источника"
    assert show.doubted == set() and show.offline == ""


def test_a_torn_print_in_the_blame_does_not_silence_the_next_attempt(tmp_path: Path) -> None:
    """Разбор обрыва печатает - и печать рвётся: замок починки не может остаться закрытым.

    Между взятием замка и подъёмом лежит весь разбор обрыва, а он и печатает, и читает
    лог прогона: `BrokenPipeError` и `OSError` тут не выдумка. Замок, оставшийся
    закрытым от такого броска, не отпустит уже никто, и починка ленты умолкнет до конца
    показа молча.
    """

    def torn_pipe(_line: str) -> None:
        raise BrokenPipeError("печать оборвалась")

    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path, log=torn_pipe)
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=1))

    with pytest.raises(BrokenPipeError, match="печать оборвалась"):
        _sweep(show, asked.append)
    show.log = None
    tract(now=110.0, spawn=here)
    _sweep(show, asked.append)

    assert asked == [3], "брошенный разбор обрыва навсегда занял замок починки"


def test_a_show_already_over_is_not_given_a_run_to_kill(tmp_path: Path) -> None:
    """Признак конца встал до подъёма - прогон не поднимается вовсе, и снос его не ждёт.

    Внутри подъёма лежит пробный прогон, до минуты по потолку, а снос показа стоит за
    этим замком: замер на сухом стенде с висящим источником - 59.76 с ожидания ради
    прогона, который тут же и гасят.
    """
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path)
    show.fatal = "показ окончен"
    assert show.lock.acquire(blocking=False), "замок ленты свободен до пробы"

    _lift(show, asked.append, 3)

    assert asked == [], "подъём поднял прогон показу, которого уже нет"
    assert show.lock.acquire(blocking=False), "подъём не отпустил замок"
    show.lock.release()


def test_a_run_torn_by_itself_is_lifted_where_it_broke_even_behind_the_viewer(
    tmp_path: Path,
) -> None:
    """🔴 TC-634. Показ давно ушёл вперёд, а подъём оборванного прогона остался прежним.

    Развязка спора о хозяине ленты
    (:func:`torrcast.usecases.feed_pack.feed_steer._behind`) читает место зрителя, которое
    кладёт сюда уборка, и заткнуть она обязана только «место сменил зритель». «Порвалось
    само» - случай другой и починки не лишается: подъём продолжает прогон там, где тот
    оборвался, а не там, где стоит зритель.

    Место подъёма тут нарочно позади зрителя - ровно то, которое запрос сегмента уже не
    считает своим. Загнать сюда ту же границу значило бы оставить показ без починки обрыва
    на весь остаток фильма: полке впереди зрителя взяться было бы неоткуда.
    """
    tract(now=100.0, spawn=here)
    asked: list[int] = []
    show = feed(tmp_path, grid=grid(7800.0, 10.0))
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=FakeProc(code=1))
    show.prune(900.0)  # круг часов показа: зритель давно за окном keep от этого места

    _sweep(show, asked.append)

    assert asked == [3], "оборванный сам прогон лишился подъёма из-за развязки перемотки"
    assert show.crashes == 1 and show.restarted == 100.0
