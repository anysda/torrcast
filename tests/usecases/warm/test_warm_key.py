"""Ключ каталога прогретого: он обязан меняться от всего, что меняет байты куска."""

from __future__ import annotations

from dataclasses import dataclass

from tests.usecases.warm.world import grid
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.usecases.warm.warm_key import warm_key

SOURCE = "http://ts/stream?link=abc&index=1"


@dataclass(frozen=True)
class _Encode:
    preset: str = "ultrafast"
    mbit: float = 9.0
    mark: str = ""


def test_the_same_show_gets_the_same_key() -> None:
    """Ключ стабилен: иначе прогретое своего же показа не нашлось бы после перезапуска."""
    assert warm_key(SOURCE, 0, grid()) == warm_key(SOURCE, 0, grid())
    assert len(warm_key(SOURCE, 0, grid())) == 16


def test_another_file_track_or_grid_is_another_catalogue() -> None:
    """Разошлось содержимое куска - разошёлся и каталог, иначе показ отдаст не то кино."""
    base = warm_key(SOURCE, 0, grid())

    assert base != warm_key(SOURCE.replace("index=1", "index=2"), 0, grid()), "другой файл"
    assert base != warm_key(SOURCE, 1, grid()), "другая дорожка"
    assert base != warm_key(SOURCE, 0, grid(duration=120.0)), "другая сетка"


def test_the_origin_of_the_timeline_is_part_of_the_key() -> None:
    """Начало ленты - тоже содержимое куска: на чужой ленте метки пошли бы назад."""
    from dataclasses import replace

    shifted = replace(grid(), origin=0.5)

    assert warm_key(SOURCE, 0, grid()) != warm_key(SOURCE, 0, shifted)


def test_the_recode_and_the_spots_change_the_key_too() -> None:
    """Перекод и список тяжёлых мест меняют байты под теми же именами."""
    base = warm_key(SOURCE, 0, grid())

    assert base != warm_key(SOURCE, 0, grid(), _Encode()), "перекод"
    assert warm_key(SOURCE, 0, grid(), _Encode()) != warm_key(
        SOURCE, 0, grid(), _Encode(mbit=4.0)
    ), "другой битрейт перекода"
    assert warm_key(SOURCE, 0, grid(), _Encode()) != warm_key(
        SOURCE, 0, grid(), _Encode(mark="720p")
    ), "ужатый кадр под другой приёмник"
    assert base != warm_key(SOURCE, 0, grid(), None, (1, 2)), "точечные перекоды"
    assert warm_key(SOURCE, 0, grid(), None, (1, 2)) != warm_key(SOURCE, 0, grid(), None, (1, 3))


def test_the_grid_that_moved_its_bounds_is_another_catalogue() -> None:
    """Сдвинулись сами резы, а число их прежнее - каталог обязан быть другим.

    Правило реза двигает границы, не трогая их количества: короткий хвост прилипает к
    последнему куску и съедает лишний рез. Кусок ``v2`` тут занимает 10.0-20.0 с в одной
    сетке и 10.0-22.0 с в другой; ляг они в один каталог, показ отдал бы приёмнику кусок
    старых границ под именем новых, и на стыке метки пошли бы назад.
    """
    before = Grid(bounds=(0.0, 10.0, 20.0, 34.0), duration=40.0, on_keys=True)
    after = Grid(bounds=(0.0, 10.0, 22.0, 34.0), duration=40.0, on_keys=True)

    # Случай ловится ровно границами, а не чужой причиной: всё прочее у сеток совпадает.
    assert before.count == after.count, "число кусков разошлось - случай не тот"
    assert (before.duration, before.on_keys, before.origin) == (
        after.duration,
        after.on_keys,
        after.origin,
    ), "сетки разошлись не границами - случай не тот"

    assert warm_key(SOURCE, 0, before) != warm_key(SOURCE, 0, after)
