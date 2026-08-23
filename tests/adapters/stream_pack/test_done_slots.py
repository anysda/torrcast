"""Дописанность куска: мало открыть следующий, надо ещё дорезать хвост до конца фильма."""

from __future__ import annotations

import dataclasses
from typing import TYPE_CHECKING, Any

from tests.usecases.feed_pack.world import packer
from torrcast.adapters.stream_pack.done_slots import done_slots
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.domain.hls_settings import PACK_LIST, PACK_SHORT_SECONDS
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install

if TYPE_CHECKING:
    from pathlib import Path

GRID = Grid.uniform(40.0, 10.0)
#: Последний кусок сетки - тот единственный, чей конец ставит не рез, а конец входа.
TAIL = GRID.count - 1


class _Spy(Silent):
    """Молчащая лента, которая запоминает отметки: обрезок обязан оставить след."""

    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, Any]]] = []

    def mark(self, name: str, **facts: Any) -> None:
        self.marks.append((name, facts))


def _cut_list(run: Path, ends: dict[int, float], grid: Grid = GRID) -> None:
    """Список нарезки, который ведёт сам ffmpeg: имя, начало и КОНЕЦ закрытого куска."""
    lines = [f"v{slot}.ts,{grid.start(slot):.6f},{over:.6f}" for slot, over in sorted(ends.items())]
    (run / PACK_LIST).write_text("\n".join(lines) + "\n", encoding="utf-8")


def _whole(grid: Grid = GRID) -> dict[int, float]:
    """Список нарезки здорового захода: каждый кусок закрыт ровно на своей границе."""
    return {slot: grid.end(slot) + grid.origin for slot in range(grid.count)}


def test_a_tail_cut_short_of_the_end_of_the_film_is_not_done(tmp_path: Path) -> None:
    """🔴 TC-771. Хвост, закрытый раньше конца фильма, дописанным не считается.

    Сосед у него есть - муксер открывает следующий файл и после реза по своему умолчанию,
    - и по одному этому признаку обрезок проходил дальше как готовый. Имя и начало у него
    верные, длину не сверял никто, и зритель терял конец фильма.
    """
    run = packer(tmp_path, grid=GRID)
    _cut_list(run.run, {**_whole(), TAIL: GRID.start(TAIL) + 2.0})

    assert done_slots(run, list(range(GRID.count)), True) == list(range(TAIL)), (
        "обрезанный хвост ушёл дальше как дописанный"
    )


def test_a_tail_that_reached_the_end_of_the_film_is_done(tmp_path: Path) -> None:
    """Отрицательная проба: честно дорезанный хвост мера не трогает."""
    run = packer(tmp_path, grid=GRID)
    _cut_list(run.run, _whole())

    assert done_slots(run, list(range(GRID.count)), True) == list(range(GRID.count))


def test_the_legal_undershoot_at_the_end_of_the_film_is_not_a_break(tmp_path: Path) -> None:
    """Хвост вправе не дотянуть до обещанного: длительность берётся из контейнера, а поток
    кончается на последнем пакете.

    Допуск тут не выбран, а замерен (:data:`PACK_SHORT_SECONDS`): законный недобор -
    0.000-0.065 с, обрыв даёт 0.6-10.0 с. Числа пробы считаются от самого допуска, а не
    вписаны рядом с ним.
    """
    run = packer(tmp_path, grid=GRID)
    whole = list(range(GRID.count))

    _cut_list(run.run, {**_whole(), TAIL: GRID.end(TAIL) - PACK_SHORT_SECONDS / 2})
    assert done_slots(run, whole, True) == whole

    _cut_list(run.run, {**_whole(), TAIL: GRID.end(TAIL) - PACK_SHORT_SECONDS * 2})
    assert done_slots(run, whole, True) == whole[:TAIL]


def test_a_piece_in_the_middle_that_ends_early_is_left_to_the_guard_of_the_beginning(
    tmp_path: Path,
) -> None:
    """🔴 Кусок НЕ последнего места длиной здесь не судится, и это не поблажка.

    Его конец ставит рез, а рез отмеряется от первого пакета прогона: заход, вставший не
    туда, уводит весь свой участок целиком, куски при этом полной длины, и разбирается с
    этим сверка НАЧАЛА - она умеет и переложить место, и объявить его непрогретым. Отбери
    у неё такой кусок здесь, и вместо переклада вышел бы вечный круг «прогрев не дал ни
    куска».
    """
    run = packer(tmp_path, grid=GRID)
    shifted = {slot: over - 1.5 for slot, over in _whole().items()}

    assert done_slots(run, list(range(GRID.count - 1)), True) == list(range(GRID.count - 1))
    _cut_list(run.run, shifted)
    assert done_slots(run, list(range(GRID.count - 1)), True) == list(range(GRID.count - 1))


def test_the_origin_of_the_tape_is_subtracted_before_the_comparison(tmp_path: Path) -> None:
    """ffmpeg пишет в свой список уже сдвинутые метки: без вычитания начала ленты
    «недобор» показывал бы ровно этот сдвиг на каждом релизе с B-кадрами.
    """
    lifted = dataclasses.replace(GRID, origin=1.0)
    run = packer(tmp_path, grid=lifted)
    _cut_list(run.run, _whole(lifted), grid=lifted)

    assert done_slots(run, list(range(lifted.count)), True) == list(range(lifted.count))


def test_the_stub_beyond_the_pass_is_not_judged_by_length(tmp_path: Path) -> None:
    """Обрезок за ``-to`` короче своего места по замыслу: выкладка отбрасывает его сама.

    Заход, который до хвоста сетки не дошёл вовсе, судить тут нечем: его последний кусок
    закрыт резом, а не концом входа.
    """
    run = packer(tmp_path, grid=GRID, last=TAIL - 1)
    _cut_list(run.run, {**_whole(), TAIL: GRID.start(TAIL) + 1.0})

    assert done_slots(run, list(range(GRID.count)), True) == list(range(GRID.count))


def test_a_tail_with_no_line_in_the_list_goes_out_as_before(tmp_path: Path) -> None:
    """⚠️ Молчание списка нарезки - не признак обрезка, и мера на нём не строится.

    Список читается с диска, и отказ чтения обнулил бы его целиком: выкладка встала бы
    насмерть там, где всё в порядке.
    """
    run = packer(tmp_path, grid=GRID)

    assert done_slots(run, list(range(GRID.count)), True) == list(range(GRID.count))


def test_a_run_without_a_grid_has_nothing_to_compare_with(tmp_path: Path) -> None:
    """Сетки у прогона может не быть вовсе - тогда сверять не с чем и мера молчит."""
    run = packer(tmp_path)
    _cut_list(run.run, dict.fromkeys(range(GRID.count), 1.0))

    assert done_slots(run, list(range(GRID.count)), True) == list(range(GRID.count))


def test_the_last_piece_still_waits_for_the_run_to_read_the_input(tmp_path: Path) -> None:
    """Прежний признак никуда не делся: без ``finished`` последний кусок не дописан."""
    run = packer(tmp_path, grid=GRID)
    _cut_list(run.run, _whole())

    assert done_slots(run, list(range(GRID.count)), False) == list(range(TAIL))


def test_a_short_tail_is_a_record_with_numbers(tmp_path: Path) -> None:
    """Обрезок называется в журнале числами: без них разбор упирается в «кусок не вышел»."""
    spy = _Spy()
    install(spy)
    run = packer(tmp_path, grid=GRID)
    _cut_list(run.run, {**_whole(), TAIL: GRID.start(TAIL) + 2.0})

    done_slots(run, list(range(GRID.count)), True)

    said = [facts for name, facts in spy.marks if name == "хвост короче своей границы"]
    assert said and said[0] == {
        "слот": TAIL,
        "граница": round(GRID.end(TAIL), 3),
        "замер": round(GRID.start(TAIL) + 2.0, 3),
    }
