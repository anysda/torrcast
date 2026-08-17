"""Пора ли открыть ворота отбора: живого именного кандидата у картины нет."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.gate_open import gate_open

QUIET = {"quality": None, "codec": None, "source": None}


def test_gates_stay_shut_while_a_live_named_candidate_is_around() -> None:
    assert not gate_open([rel(seeders=100)], RUNTIME, 20.0)


def test_gates_open_when_the_named_candidates_are_gone() -> None:
    """«Наруто»: полный сериал на 91 сид в кандидаты не проходит вовсе."""
    naruto = rel(name="Наруто [E220 of 220] DVDRip", seeders=91, **QUIET)  # type: ignore[arg-type]
    assert gate_open([naruto], RUNTIME, 20.0)


def test_a_barely_alive_candidate_does_not_hold_the_gates() -> None:
    """Живость тут доля от лидера пула: 10 сидов против 100 - это не защита от мусора."""
    lead = rel(name="молчун", seeders=100, **QUIET)  # type: ignore[arg-type]
    faint = rel(name="именной", seeders=10)
    assert gate_open([lead, faint], RUNTIME, 20.0)


def test_an_all_dead_pool_leaves_the_gates_shut() -> None:
    """Открывать их незачем: показывать всё равно нечего.

    ⚠️ Мёртвый пул спрашивается ДВАЖДЫ, и второй раз - молчаливыми именами. У именного
    мертвеца ворота держит он сам: кандидатом он остаётся, и снятая проверка на нулевого
    лидера ничего бы не изменила. Спор ровно там, где живых нет и кандидатов нет: доля
    от нуля проходит у кого угодно, и без проверки ворота открылись бы пустому пулу.
    """
    assert not gate_open([rel(seeders=0)], RUNTIME, 20.0)
    quiet = rel(name="молчун", seeders=0, **QUIET)  # type: ignore[arg-type]
    assert not gate_open([quiet], RUNTIME, 20.0)
