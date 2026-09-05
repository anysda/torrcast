"""Сверка уложенного с сеткой: кусок обязан начаться там, где обещал манифест."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from typing import TYPE_CHECKING

from tests.usecases.warm.world import grid, lay, warmer, world
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.warm.segment_start import _Clock
from torrcast.usecases.warm.settings import SKEW_MAX, SKEW_TRIES
from torrcast.usecases.warm.verify import BLIND, FIT, SKEW, _inspect, _verify

if TYPE_CHECKING:
    from pathlib import Path


def _began(starts: dict[int, float], *, movie: bool = True) -> Callable[[Path], _Clock]:
    """Начало каждого куска под рукой зеркала: слот берётся из имени файла."""
    return lambda path: _Clock(starts.get(int(path.stem[1:]), float("nan")), movie=movie)


def test_a_piece_on_its_border_passes(tmp_path: Path) -> None:
    """Кусок, начавшийся на своей границе, остаётся лежать и в показ идёт."""
    world()
    warm = warmer(tmp_path)
    lay(warm.vault, 2)
    began = _began({2: 20.0})

    assert _verify(warm, 2, began) == FIT
    assert warm.vault.have(2) and warm.misgrid == -1


def test_a_piece_later_than_its_border_is_legal_too(tmp_path: Path) -> None:
    """Позже границы кусок начаться может законно: муксер ждёт следующего опорного кадра."""
    world()
    warm = warmer(tmp_path)
    lay(warm.vault, 2)
    began = _began({2: 21.4})

    assert _verify(warm, 2, began) == FIT and warm.vault.have(2)


def test_a_piece_before_its_border_is_wiped_and_stops_the_run(tmp_path: Path) -> None:
    """Раньше границы кусок начаться не может ни по одной законной причине."""
    fake = world()
    said: list[str] = []
    warm = warmer(tmp_path, log=said.append)
    lay(warm.vault, 2)
    warm.vault.served.mark(2)
    began_value = 20.0 - SKEW_MAX - 1.0
    began = _began({2: began_value})

    assert _verify(warm, 2, began) == SKEW
    assert not warm.vault.have(2), "кусок мимо сетки остался в показе"
    assert not warm.vault.spot(2).exists(), "метка перекода пережила забракованный кусок"
    assert 2 not in warm.vault.served, "раздача запомнила уже забракованный перекод"
    assert warm.misgrid == 2, "заход не оборвался на промахе"
    assert warm.skews[2] == 1
    assert fake.events[0][0] == "skew" and fake.events[0][2]["hole"] is False
    assert not warm.trouble, "первый промах объявлен дырой без второй попытки"

    # Первый промах не молчит: зритель обязан узнать, что прогрев повторит попытку,
    # а не просто тихо стёр кусок с диска.
    want = warm.grid.start(2) + warm.grid.origin
    where = phrase(
        "warm.skew_where", slot=2, minute=f"{want / 60:.0f}", diff=f"{began_value - want:+.2f}"
    )
    assert said == [phrase("warm.skew_retry", where=where)]


def test_the_second_miss_on_the_same_place_is_a_hole(tmp_path: Path) -> None:
    """Второй промах на том же месте - не случайность, а поломка упаковки."""
    world()
    warm = warmer(tmp_path, log=[].append)
    began = _began({2: 0.0})
    for _ in range(SKEW_TRIES):
        lay(warm.vault, 2)
        warm.misgrid = -1
        _verify(warm, 2, began)

    hole_tail = phrase("warm.skew_hole", where="WHERE-MARK").split("WHERE-MARK")[1]
    assert warm.skews[2] == SKEW_TRIES
    assert hole_tail in warm.trouble, "прогрев ходит кругами по одному месту"


def test_the_origin_of_the_timeline_is_added_to_the_border(tmp_path: Path) -> None:
    """Метка куска - это время фильма ПЛЮС начало ленты: иначе порог съеден до промаха."""
    world()
    warm = warmer(tmp_path, grid=replace(grid(), origin=1.0))
    lay(warm.vault, 2)
    began = _began({2: 20.5})

    assert _verify(warm, 2, began) == SKEW, "начало ленты не прибавили - промах прошёл за здоровый"

    warm.misgrid = -1
    lay(warm.vault, 2)
    began = _began({2: 21.0})
    assert _verify(warm, 2, began) == FIT


def test_an_unreadable_piece_is_never_thrown_away(tmp_path: Path) -> None:
    """Сторож, который бракует по незнанию, дороже дефекта: кусок остаётся лежать."""
    world()
    warm = warmer(tmp_path)
    lay(warm.vault, 2)
    began = _began({})

    assert _verify(warm, 2, began) == BLIND and warm.vault.have(2)


def test_an_unreadable_piece_is_not_called_fit(tmp_path: Path) -> None:
    """🔴 TC-879. Сторож, не сумевший прочесть, обязан сказать это вслух, а не зеленеть.

    Раньше здесь стояла годность, и на приставке она держалась на КАЖДОМ куске: ложная
    зелень ровно там, где мерить нечем.
    """
    fake = world()
    said: list[str] = []
    warm = warmer(tmp_path, log=said.append)
    lay(warm.vault, 2)

    assert _verify(warm, 2, _began({})) != FIT, "сторож зелен там, где мерить не может"
    assert warm.unchecked == 1
    assert fake.marks[0][0] == "укладку прогрева не с чем сверить"
    why = phrase("warm.blind_why_timecode")
    blind_head = phrase("warm.blind_note", why="WHY-MARK").split("WHY-MARK")[0]
    assert blind_head in said[0] and why in said[0]


def test_the_counter_of_the_run_is_never_compared_to_the_grid(tmp_path: Path) -> None:
    """Число прочлось, но лента у него не фильма: сверять его с сеткой нечем (CMAF).

    Промахом такой кусок звать нельзя: 23.982 с ленты прогона против границы 20 с - это
    не сдвиг, а разные единицы, и стёрли бы тут здоровый кусок.
    """
    world()
    warm = warmer(tmp_path, log=[].append)
    lay(warm.vault, 2)
    began = _began({2: 23.982}, movie=False)

    assert _verify(warm, 2, began) == BLIND
    assert warm.vault.have(2) and warm.misgrid == -1 and not warm.skews


def test_the_blindness_is_said_once_per_warm_and_not_once_per_piece(tmp_path: Path) -> None:
    """Слепота тут свойство контейнера: тысяча одинаковых строк не громче одной."""
    world()
    said: list[str] = []
    warm = warmer(tmp_path, log=said.append)
    for slot in range(4):
        lay(warm.vault, slot)

    _inspect(warm, -1, 3, _began({}, movie=False))

    assert warm.unchecked == 4 and len(said) == 1
    assert warm.vault.slots() == {0, 1, 2, 3}, "несверенное выброшено"


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
