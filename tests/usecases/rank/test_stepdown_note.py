"""Строка о том, что показ едет ступенью ниже доступной; молчаливых подмен нет."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tests.usecases.rank.releases import RUNTIME, media, rel
from torrcast.domain.episode import Episode
from torrcast.domain.release import Release
from torrcast.usecases.rank.stepdown_note import STEP_RATIO, stepdown_note


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка про снижение ступени, писанная до языкового яруса."""


@dataclass
class Plan:
    """Ровно то, что правило у плана и спрашивает."""

    ranked: list[Release] = field(default_factory=list)
    want: Episode | None = None
    runtime: float = RUNTIME
    warn_mbit: float = 20.0
    hard_mbit: float = 0.0
    copy_hevc: bool = False
    last_resort: bool = False


def test_nothing_better_around_means_no_line() -> None:
    """Лишняя строка на каждом показе обесценивает все остальные."""
    assert stepdown_note(Plan([rel(name="полный", quality="1080p")]), 1, media(), [1]) == ""


def test_the_line_names_what_was_taken_and_what_stood_nearby() -> None:
    """🔴 TC-187. «Интерстеллар» доезжал в 720p при живых 1080p, и никто об этом не говорил."""
    taken, near = rel(name="взятый", quality="720p"), rel(name="сосед", seeders=59)
    said = stepdown_note(Plan([taken, near]), 1, media(height=720, width=1280), [1, 2], reached=1)

    assert said == "взял 720p, рядом был 1080p (релиз 2, сидов 59) - не дошли"


def test_the_taken_one_is_measured_by_its_passport_not_by_its_name() -> None:
    """Иначе строка молчала бы ровно там, где подмена и случилась."""
    taken, near = rel(name="взятый", quality="1080p"), rel(name="сосед", seeders=59)
    said = stepdown_note(Plan([taken, near]), 1, media(height=574, width=1150), [1, 2], reached=1)

    assert said.startswith("взял 574p, рядом был 1080p (релиз 2, сидов 59)")


def test_a_dead_best_is_named_as_a_dead_swarm() -> None:
    taken, near = rel(name="взятый", quality="720p"), rel(name="сосед", seeders=0)
    said = stepdown_note(Plan([taken, near]), 1, media(height=720, width=1280), [1, 2])

    assert said.endswith("рой мёртв")


def test_a_rounding_difference_is_not_a_step() -> None:
    """1080 против 1078 - это округление разных рипов одного и того же мастера."""
    assert STEP_RATIO == 0.95
    plan = Plan([rel(name="взятый", quality="1080p"), rel(name="сосед", quality="1080p")])
    assert stepdown_note(plan, 1, media(), [1, 2]) == ""


def test_a_neighbour_that_was_touched_and_turned_down_carries_its_verdict() -> None:
    """Лучшего трогали и осудили - в строке стоит его приговор, а не «не дошли».

    Разница не косметическая: «не дошли» значит «попробуй ещё раз», а приговор роя или
    ffprobe - что пробовать нечего, и следующий заход кончится тем же.
    """
    taken, near = rel(name="взятый", quality="720p"), rel(name="сосед", seeders=59)
    said = stepdown_note(
        Plan([taken, near]), 1, media(height=720, width=1280), [2, 1], {2: "рой молчит"}, 2
    )

    assert "отбраковали (рой молчит)" in said


def test_a_neighbour_that_kept_silent_is_not_called_turned_down() -> None:
    """До ответа роя приговора релизу нет: кончилось только НАШЕ ожидание."""
    taken, near = rel(name="взятый", quality="720p"), rel(name="сосед", seeders=59)
    said = stepdown_note(Plan([taken, near]), 1, media(height=720, width=1280), [2, 1], {}, 2)

    assert said.endswith("не ответил")
    assert "отбраковали" not in said
