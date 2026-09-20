"""Длительность карточки: настоящая от справки, когда та её знает, иначе честная прикидка."""

from __future__ import annotations

from torrcast.domain.facts.fact import Fact
from torrcast.domain.picture import Picture
from torrcast.usecases.select.plan import Plan
from web.display_runtime import display_runtime

_PICTURE = Picture(title="It", year=2017, kind="movie", original="It")
#: 2 ч 15 мин настоящей длительности - как у "Оно" (2017), ТС-1282.
_IT_RUNTIME = "2 ч 15 мин"


def _plan(runtime: float, estimated: bool) -> Plan:
    return Plan(
        picture=_PICTURE, ranked=[], runtime=runtime, warn_mbit=12.0, runtime_estimated=estimated
    )


def test_real_runtime_replaces_the_guess_when_the_fact_knows_it() -> None:
    plan = _plan(runtime=7200.0, estimated=True)
    fact = Fact(runtime=_IT_RUNTIME)

    runtime, estimated = display_runtime(plan, fact)

    assert runtime == 135 * 60.0
    assert estimated is False


def test_guess_stays_the_guess_when_the_fact_is_silent() -> None:
    plan = _plan(runtime=7200.0, estimated=True)

    runtime, estimated = display_runtime(plan, Fact())

    assert runtime == 7200.0
    assert estimated is True


def test_measured_file_passport_is_not_overruled_by_the_fact() -> None:
    """TC-819: паспорт файла (`runtime_estimated=False`) справка не перебивает."""
    plan = _plan(runtime=8520.0, estimated=False)
    fact = Fact(runtime=_IT_RUNTIME)

    runtime, estimated = display_runtime(plan, fact)

    assert runtime == 8520.0
    assert estimated is False
