"""Уборка кусков прогрева, которые приёмник не сможет взять."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import grid, lay, vault, world
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.usecases.warm.trim import trim

if TYPE_CHECKING:
    from pathlib import Path

#: Осторожный потолок веса куска, байты (Samsung Q70D).
CAP = 16_000_000
#: Сетка живого замера: файл 10 Мбит/с, опорный кадр каждые 8.5 с, фильм 186.65 с.
#: Осторожный потолок режет её по 8.5 с, и хвост остаётся один - 16.65 с.
MEASURED = Grid(tuple(8.5 * k for k in range(21)), 186.65, True)
#: Что в этой сетке весит обычный кусок и что весит её хвост - оба числа замерены
#: настоящей упаковкой, а не посчитаны.
PIECE = 11_040_000
TAIL = 21_630_000


def test_only_pieces_above_the_receivers_cap_are_removed(tmp_path: Path) -> None:
    world()
    store = vault(tmp_path)
    lay(store, 0, size=100)
    lay(store, 1, size=101)
    store.spot(1).touch()

    assert trim(store, 100, grid()) == (1, 101)

    assert store.slots() == {0}
    assert not store.spot(1).exists(), "метка пережила невыдаваемый кусок"


def test_the_last_piece_of_the_film_survives_the_cautious_cap(tmp_path: Path) -> None:
    """Хвост тяжелее потолка ПО ПОСТРОЕНИЮ, и уборке он не добыча.

    Замер: обычный кусок 8.5 с весит 11.04 МБ при потолке 16, а хвост 16.65 с - 21.63 МБ.
    Забери его уборка - прогрев сделал бы его заново, и следующий старт забрал бы снова.
    """
    world()
    store = vault(tmp_path)
    lay(store, 19, size=PIECE)
    lay(store, 20, size=TAIL)

    assert trim(store, CAP, MEASURED) == (0, 0)

    assert store.slots() == {19, 20}, "уборка забрала законный хвост фильма"


def test_a_glued_together_catalogue_loses_its_tail_too(tmp_path: Path) -> None:
    """Прибавка хвосту - доля, а не индульгенция: слипшийся кусок она не спасает.

    Ровно тот мусор, ради которого уборка и заведена: 243 МБ на месте хвоста при
    потолке 16 - это не хвост, а весь фильм одним файлом.
    """
    world()
    store = vault(tmp_path)
    lay(store, 20, size=243_000_000)

    assert trim(store, CAP, MEASURED) == (1, 243_000_000)

    assert store.slots() == set(), "слипшийся кусок пережил уборку"


def test_a_short_tail_gets_no_allowance_at_all(tmp_path: Path) -> None:
    """Хвост короче обычного куска судится общим потолком: прибавке там неоткуда взяться."""
    world()
    store = vault(tmp_path)
    short = Grid((0.0, 17.0, 34.0, 51.0), 55.0, True)
    lay(store, 3, size=CAP + 1)

    assert trim(store, CAP, short) == (1, CAP + 1)

    assert store.slots() == set()


def test_a_heavy_copy_awaiting_its_spot_recode_is_left_alone(tmp_path: Path) -> None:
    """Тяжёлая копия под точечный перекод - работа впереди, а не мусор.

    Прогрев кладёт тяжёлое место сперва копией во весь вес, а ужимает его поздним
    точечным перекодом уже на диске. Замер на настоящем каталоге посреди прогрева
    («Дюна: Часть вторая», 1080p 11.9 Мбит/с): 105 кусков, 64 тяжелее потолка, и 59 из
    них - цели перекода, 1.32 ГБ. Забери их уборка - продолжение показа тянуло бы их
    из роя заново каждый вечер.
    """
    world()
    store = vault(tmp_path)
    lay(store, 1, size=CAP + 5_000_000)
    lay(store, 2, size=CAP * 3)

    assert trim(store, CAP, grid(), spots=(1,)) == (1, CAP * 3)

    assert store.slots() == {1}, "уборка забрала копию, которую ещё перекодируют"


def test_a_spot_that_stayed_heavy_after_its_recode_is_removed(tmp_path: Path) -> None:
    """Перекод по месту уже прошёл, а легче не стало: чинить его больше некому."""
    world()
    store = vault(tmp_path)
    lay(store, 1, size=CAP + 5_000_000)
    store.spot(1).touch()

    assert trim(store, CAP, grid(), spots=(1,)) == (1, CAP + 5_000_000)

    assert store.slots() == set()
    assert not store.spot(1).exists(), "метка пережила невыдаваемый кусок"
