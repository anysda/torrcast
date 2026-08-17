"""Куда идти прогреву: сначала хвост от места показа, потом голова фильма."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.warm.world import lay, warmer
from torrcast.usecases.warm.missing import _missing, _pending

if TYPE_CHECKING:
    from pathlib import Path


def test_the_tail_from_the_show_comes_first(tmp_path: Path) -> None:
    """Обрыв связи бьёт по будущему, а не по пройденному: хвост важнее головы."""
    warm = warmer(tmp_path, began_at=3)

    assert _missing(warm) == (3, warm.grid.count - 1)


def test_the_head_is_taken_only_after_the_tail_is_whole(tmp_path: Path) -> None:
    """Голова берётся, когда хвост уже лежит целиком, и прогон кончается на месте показа."""
    warm = warmer(tmp_path, began_at=3)
    for slot in range(3, warm.grid.count):
        lay(warm.vault, slot)

    assert _missing(warm) == (0, 2), "голова не взялась или заехала за место показа"


def test_a_hole_in_the_tail_is_taken_before_the_head(tmp_path: Path) -> None:
    """Дыра в хвосте важнее головы: под ней показу нужна сеть прямо сейчас."""
    warm = warmer(tmp_path, began_at=3)
    for slot in (3, 5):
        lay(warm.vault, slot)

    assert _missing(warm) == (4, warm.grid.count - 1)


def test_a_whole_film_leaves_nowhere_to_go(tmp_path: Path) -> None:
    """Всё лежит - идти некуда, и это не ошибка, а конец работы."""
    warm = warmer(tmp_path)
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    assert _missing(warm) is None
    assert not _pending(warm), "работа кончилась, а прогрев считает её незаконченной"


def test_a_heavy_place_still_counts_as_work_left(tmp_path: Path) -> None:
    """Место под точечный перекод - тоже работа: цепочка серий ждёт именно её конца."""
    warm = warmer(tmp_path, spots=(2,), spot_encode=object())
    for slot in range(warm.grid.count):
        lay(warm.vault, slot)

    assert _missing(warm) is None and _pending(warm), "тяжёлое место выпало из работы"

    warm.vault.spot(2).touch()
    assert not _pending(warm)


def test_a_measured_by_the_cap_reserve_does_not_move_the_warming(tmp_path: Path) -> None:
    """Прогреву место видно уложенным даже тяжёлой копией - иначе он клал бы его вечно."""
    warm = warmer(tmp_path, cap=500)
    for slot in range(warm.grid.count):
        lay(warm.vault, slot, size=1000)

    assert warm.warmed == 0.0, "тяжёлые копии зачлись запасом показа"
    assert _missing(warm) is None, "прогрев пошёл перекладывать уже уложенное"
