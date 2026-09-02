"""Долив опоздавшего индексера в пул уже выбранной картины."""

from __future__ import annotations

from typing import Any

from tests.usecases.reinforce.stand import Said, pictures, row
from torrcast.domain.args import Args
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.reinforce._topup import _topup
from torrcast.usecases.reinforce.plan_for import plan_for


def _poured(rows: list[RawResult], menu: frozenset[str] = frozenset()) -> tuple[Any, Any, Said]:
    """План на одной раздаче, в который опоздавший индексер доливает свои строки."""
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a", seeders=100)])[0]
    plan = plan_for(picture, Args(query=["кино"]), Config())
    plan.late = lambda: rows
    said = Said()
    fresh = _topup(plan, Args(query=["кино"]), Config(), CAUTIOUS, said, menu)
    return plan, fresh, said


def test_the_late_indexer_fills_the_pool_of_the_chosen_picture() -> None:
    """🔴 TC-118. Круг ушёл по кворуму, опоздавший доехал, пока человек читал меню."""
    plan, fresh, said = _poured([row("Кино / Movie (1999) BDRip 2160p", "b", seeders=900)])

    assert len(fresh.picture.releases) == 2
    assert fresh.picture.key == plan.picture.key, "подменять картину долив не вправе"
    line = phrase("reinforce.arrived_after_list", who="Nyaa.si") + phrase(
        "reinforce.topup_counts", now=2, was=1
    )
    assert line in said.text


def test_a_new_top_of_the_queue_is_said_out_loud() -> None:
    """Верх отбора долив поменять вправе - выбирали картину, а не раздачу, - но не молча."""
    _plan, fresh, said = _poured([row("Кино / Movie (1999) BDRip 1080p x264", "c", seeders=900)])

    assert fresh.ranked[0].seeders == 900
    assert phrase("reinforce.topup_changed") in said.text


def test_a_picture_outside_the_menu_does_not_enter_it() -> None:
    """Предложить её уже некому, но и молча она не пропадает (TC-238)."""
    plan, fresh, said = _poured([row("Другое / Other (2001) BDRip 1080p", "d", seeders=900)])

    assert fresh is plan, "чужая картина плана не меняет вовсе"
    assert phrase("reinforce.foreign_brought", names="«Другое» (2001)") in said.text


def test_an_empty_late_batch_leaves_the_plan_as_it_was() -> None:
    """Опоздавший так и не доехал - план прежний, и ни одной лишней строки."""
    plan, fresh, said = _poured([])

    assert fresh is plan
    assert said.notes == []


def test_a_topup_that_reaches_no_selection_at_all_is_not_boasted_about() -> None:
    """Долив мимо отбора плану ничего не даёт, и строки про него быть не должно.

    Спрошен первый сезон, а выдача принесла пятый: в отбор не попадает ни одна раздача -
    ни прежняя, ни доехавшая. Без проверки на пустой отбор показ сказал бы «раздач стало
    больше», а выбирать из них по-прежнему нечего.
    """
    args = Args(query=["ангел", "s01e01"])
    picture = pictures([row("Ангел / Angel S05 1080p", "a", seeders=100)])[0]
    plan = plan_for(picture, args, Config())
    plan.late = lambda: [row("Ангел / Angel S05 720p", "b", seeders=900)]
    said = Said()

    fresh = _topup(plan, args, Config(), CAUTIOUS, said, frozenset())

    assert not plan.ranked, "в отборе и до долива не было ничего"
    assert fresh is plan
    assert said.notes == []


def test_the_old_releases_stay_the_very_same_objects() -> None:
    """Прогрев, пущенный под меню, ищет по ним своё новое место, а не заводится заново."""
    plan, fresh, _said = _poured([row("Кино / Movie (1999) BDRip 2160p", "b", seeders=900)])

    was = plan.picture.releases[0]

    assert any(release is was for release in fresh.picture.releases)


def test_the_measured_runtime_survives_the_topup() -> None:
    """🔴 TC-819. Долив собирает план заново, а замер длительности обратно в прикидку
    не превращается: иначе опоздавший индексер вернул бы воротам «45 минут» рядом с
    лежащим в записи паспортом.
    """
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a", seeders=100)])[0]
    plan = plan_for(picture, Args(query=["кино"]), Config(), runtime=8874.0)
    plan.late = lambda: [row("Кино / Movie (1999) BDRip 2160p", "b", seeders=900)]

    fresh = _topup(plan, Args(query=["кино"]), Config(), CAUTIOUS, Said(), frozenset())

    assert fresh is not plan, "долив собрал новый план"
    assert fresh.runtime == 8874.0
    assert not fresh.runtime_estimated


def test_the_guess_survives_the_topup_as_a_guess() -> None:
    """Прикидка доливом не «уточняется»: она остаётся оценкой и носит свой признак."""
    plan, fresh, _said = _poured([row("Кино / Movie (1999) BDRip 2160p", "b", seeders=900)])

    assert fresh.runtime == plan.runtime
    assert fresh.runtime_estimated


def test_the_memory_of_the_studio_survives_the_topup() -> None:
    """🔴 TC-701. Долив собирает план заново, а память студии решает его порядок.

    Опоздавший доезжает уже после ответа на меню, и верх отбора долив вправе сменить:
    потеряй он тут студию, сменил бы по сидам, а не по тому, чем сериал и смотрели.
    """
    picture = pictures([row("Кино / Movie (1999) BDRip 1080p", "a", seeders=100)])[0]
    plan = plan_for(picture, Args(query=["кино"]), Config())
    plan.late = lambda: [row("Кино / Movie (1999) BDRip 2160p", "b", seeders=900)]
    plan.studio = "LostFilm"

    fresh = _topup(plan, Args(query=["кино"]), Config(), CAUTIOUS, Said(), frozenset())

    assert fresh is not plan, "долив собрал новый план"
    assert fresh.studio == "LostFilm"
