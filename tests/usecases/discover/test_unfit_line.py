"""Зеркало отказа по пустой очереди: ворота отбора не пустили ни одного релиза картины."""

from __future__ import annotations

from tests.usecases.discover.world import franchise, pictures, row
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover.kin_line import _kin
from torrcast.usecases.discover.unfit_line import unfit_line
from torrcast.usecases.rank.queue_drops import queue_drops
from torrcast.usecases.reinforce.plan_for import plan_for
from torrcast.usecases.select import Plan

#: Образ диска: играть такой раздачей нечем, и ворота отбора её не пускают.
_IMAGE = row("Тачки / Cars (2006) BDRemux 2160p ISO", "a", size_gb=41.0, seeders=90)
_CARS_2 = row("Тачки 2 / Cars 2 (2011) BDRip 1080p", "b", size_gb=5.0, seeders=70)


def _plan(rows: list[RawResult], query: str = "тачки") -> Plan:
    return plan_for(franchise(query, rows)[0], Args(query=[query]), Config())


def test_the_refusal_names_the_pool_and_the_reasons_it_was_dropped_for() -> None:
    """Счёт отсева полон: ни одна раздача не пропадает молча (:func:`queue_drops`)."""
    plan = _plan([_IMAGE])

    line = unfit_line(plan, queue_drops(plan, []), [])

    assert "годного релиза нет: раздач в выдаче 1" in line
    assert "и все до одной отсеял отбор" in line


def test_living_kin_is_the_move_the_refusal_offers() -> None:
    """Ход у отказа обязан быть всегда - живого соседа по франшизе строка называет."""
    rows = [_IMAGE, _CARS_2]
    lead = franchise("тачки", rows)[0]
    plan = _plan(rows)
    kin = _kin(lead, pictures(rows), {lead.key})

    line = unfit_line(plan, queue_drops(plan, []), kin)

    assert "в каталоге есть Тачки 2 (2011)" in line
    assert "выбери руками" not in line, "раздачи отвергнуты по известным признакам"


def test_without_kin_the_move_is_another_name_or_another_day() -> None:
    """🔴 TC-447. Соседей нет - «ничего не нашлось» соврало бы: картина-то в каталоге есть."""
    plan = _plan([_IMAGE])

    line = unfit_line(plan, queue_drops(plan, []), [])

    assert "картина есть, а раздачи её негодны" in line
    assert "назови её иначе или зайди позже" in line
