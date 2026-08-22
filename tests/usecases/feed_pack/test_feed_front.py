"""Запас показа и его вес: считается от приёмника, а не глобом каталога."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import feed, grid, lay, packer, vault
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.feed_pack.feed_front import _front, _weight

if TYPE_CHECKING:
    from pathlib import Path


def test_without_a_piece_under_the_position_the_reserve_is_zero(tmp_path: Path) -> None:
    """Куска под позицией нет - запаса ноль, что бы ни лежало дальше по фильму.

    ⚠️ Раньше тут стоял глоб каталога, и после отката с 40-й минуты на 10-ю показ
    считал «впереди 1410 с» при пустом месте перед приёмником - это разрешение сторожу
    дёргать приёмник ровно тогда, когда дёргать нельзя.
    """
    show = feed(tmp_path, grid=grid(600.0, 10.0))
    for slot in range(30, 40):
        lay(show.out, slot)

    assert _front(show, played=100.0) == 100.0


def test_the_reserve_is_the_chain_of_pieces_and_it_ends_at_the_first_hole(
    tmp_path: Path,
) -> None:
    """Разрыв цепочки - конец запаса: перепрыгнуть дырку приёмник всё равно не сможет."""
    show = feed(tmp_path, grid=grid(600.0, 10.0))
    for slot in (10, 11, 12, 14):
        lay(show.out, slot)

    assert _front(show, played=105.0) == 130.0


def test_the_warmed_film_counts_as_the_reserve_of_the_show(tmp_path: Path) -> None:
    """Прогретое на диске - тот же запас: приёмнику всё равно, откуда придёт кусок."""
    store = vault(tmp_path)
    show = feed(tmp_path, grid=grid(600.0, 10.0), vault=store)
    lay(show.out, 10)
    lay(store.dir, 11)
    lay(store.dir, 12)

    assert _front(show, played=105.0) == 130.0


def test_the_reserve_never_runs_past_the_end_of_the_film(tmp_path: Path) -> None:
    """Цепочка кончается на последнем куске сетки, а не уходит за конец фильма."""
    show = feed(tmp_path, grid=grid(60.0, 10.0))
    for slot in range(6):
        lay(show.out, slot)

    assert _front(show, played=0.0) == 60.0


def test_the_memory_of_the_show_is_the_window_and_the_unclaimed_together(
    tmp_path: Path,
) -> None:
    """Память одна на оба, и вторая половина росла невидимой: число называло только первую."""
    show = feed(tmp_path)
    lay(show.out, 0, size=1000)
    lay(show.out, 1, size=1000)

    assert _weight(show) == 2000

    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 5, size=500)

    assert _weight(show) == 2500


def test_the_memory_is_named_in_full_while_the_lift_holds_the_lock(tmp_path: Path) -> None:
    """Подъём оборванного прогона держит замок ленты до минуты - вес всю её называет пик.

    Мера, отступающая перед занятым замком, ровно в эту минуту показывала бы провал
    памяти там, где растёт пик, и разбор подгрузов пошёл бы в обратную сторону.
    """
    show = feed(tmp_path)
    lay(show.out, 0, size=1000)
    show.packer = packer(tmp_path, first=0, out=show.out)
    lay(show.packer.run, 5, size=500)

    assert show.lock.acquire(blocking=False), "замок ленты свободен до пробы"
    try:
        assert _weight(show) == 1500
    finally:
        show.lock.release()


class _SwappingFeed(Feed):
    """Лента, у которой прогон исчезает ровно между двумя чтениями поля.

    Гонка тут подделана, а не поднята: второй поток дал бы то же самое, но по случаю.
    """

    reads = 0

    def __getattribute__(self, name: str) -> object:
        if name == "packer":
            type(self).reads += 1
            if type(self).reads == 2:
                self.packer = None
        return super().__getattribute__(name)


def test_the_memory_survives_the_run_swapped_between_two_readings(tmp_path: Path) -> None:
    """Прогон меняют между проверкой на ``None`` и вопросом о несданном: мера обязана устоять."""
    _SwappingFeed.reads = 0
    show = feed(tmp_path, kind=_SwappingFeed)
    lay(show.out, 0, size=1000)
    live = packer(tmp_path, first=0, out=show.out)
    lay(live.run, 5, size=500)
    show.packer = live

    assert _weight(show) == 1500
    assert _SwappingFeed.reads == 1, "поле прогона читается один раз, снимком"
