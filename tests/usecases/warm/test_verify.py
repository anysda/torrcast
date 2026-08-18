"""Сверка уложенного с сеткой: кусок обязан начаться там, где обещал манифест."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from tests.usecases.warm.world import grid, lay, warmer, world
from torrcast.usecases.warm.settings import SKEW_MAX, SKEW_TRIES
from torrcast.usecases.warm.verify import _inspect, _verify

if TYPE_CHECKING:
    from pathlib import Path


def _began(starts: dict[int, float]) -> Callable[[Path], float]:
    """Начало каждого куска под рукой зеркала: слот берётся из имени файла."""
    return lambda path: starts.get(int(path.stem[1:]), float("nan"))


def test_a_piece_on_its_border_passes(tmp_path: Path) -> None:
    """Кусок, начавшийся на своей границе, остаётся лежать и в показ идёт."""
    world()
    warm = warmer(tmp_path)
    lay(warm.vault, 2)
    began = _began({2: 20.0})

    assert _verify(warm, 2, began) is True
    assert warm.vault.have(2) and warm.misgrid == -1


def test_a_piece_later_than_its_border_is_legal_too(tmp_path: Path) -> None:
    """Позже границы кусок начаться может законно: муксер ждёт следующего опорного кадра."""
    world()
    warm = warmer(tmp_path)
    lay(warm.vault, 2)
    began = _began({2: 21.4})

    assert _verify(warm, 2, began) is True and warm.vault.have(2)


def test_a_piece_before_its_border_is_wiped_and_stops_the_run(tmp_path: Path) -> None:
    """Раньше границы кусок начаться не может ни по одной законной причине."""
    fake = world()
    warm = warmer(tmp_path, log=[].append)
    lay(warm.vault, 2)
    warm.vault.spot(2).touch()
    began = _began({2: 20.0 - SKEW_MAX - 1.0})

    assert _verify(warm, 2, began) is False
    assert not warm.vault.have(2), "кусок мимо сетки остался в показе"
    assert not warm.vault.spot(2).exists(), "метка перекода пережила забракованный кусок"
    assert warm.misgrid == 2, "заход не оборвался на промахе"
    assert warm.skews[2] == 1
    assert fake.events[0][0] == "skew" and fake.events[0][2]["hole"] is False
    assert not warm.trouble, "первый промах объявлен дырой без второй попытки"


def test_the_second_miss_on_the_same_place_is_a_hole(tmp_path: Path) -> None:
    """Второй промах на том же месте - не случайность, а поломка упаковки."""
    world()
    warm = warmer(tmp_path, log=[].append)
    began = _began({2: 0.0})
    for _ in range(SKEW_TRIES):
        lay(warm.vault, 2)
        warm.misgrid = -1
        _verify(warm, 2, began)

    assert warm.skews[2] == SKEW_TRIES
    assert "осталось непрогретым" in warm.trouble, "прогрев ходит кругами по одному месту"


def test_the_origin_of_the_timeline_is_added_to_the_border(tmp_path: Path) -> None:
    """Метка куска - это время фильма ПЛЮС начало ленты: иначе порог съеден до промаха."""
    world()
    warm = warmer(tmp_path, grid=replace(grid(), origin=1.0))
    lay(warm.vault, 2)
    began = _began({2: 20.5})

    assert _verify(warm, 2, began) is False, "начало ленты не прибавили - промах прошёл за здоровый"

    warm.misgrid = -1
    lay(warm.vault, 2)
    began = _began({2: 21.0})
    assert _verify(warm, 2, began) is True


def test_an_unreadable_piece_is_never_thrown_away(tmp_path: Path) -> None:
    """Сторож, который бракует по незнанию, дороже дефекта: ``nan`` - пропускаем."""
    world()
    warm = warmer(tmp_path)
    lay(warm.vault, 2)
    began = _began({})

    assert _verify(warm, 2, began) is True and warm.vault.have(2)


def test_the_whole_batch_is_inspected_and_not_the_first_of_it(tmp_path: Path) -> None:
    """Выкладка идёт пачкой, а промахнувшийся заход разъезжается с сеткой целиком."""
    world()
    warm = warmer(tmp_path, log=[].append)
    for slot in range(4):
        lay(warm.vault, slot)
    began = _began(dict.fromkeys(range(4), 0.0))

    assert _inspect(warm, -1, 3, began) == 3
    assert warm.vault.slots() == {0}, "проверили не всю пачку: v0 стоит на нуле законно"
    assert warm.skews == {1: 1, 2: 1, 3: 1}
