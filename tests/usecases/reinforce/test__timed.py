"""Пересборка плана на настоящей длительности картины, как только её назвала справка."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.usecases.reinforce.stand import pictures, row
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.fact import Fact
from torrcast.domain.picture import Picture
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.usecases.reinforce._timed import _timed
from torrcast.usecases.reinforce.plan_for import plan_for

#: «Интерстеллар»: у прикидки «фильм это два часа» знаменатель занижен в 1.41 раза.
_INTERSTELLAR = "2 ч 49 мин"


@dataclass
class _Facts:
    """Справка ровно в том объёме, в каком её и спрашивает пересборка плана."""

    runtime: str = ""
    asked: list[tuple[str, int | None]] = field(default_factory=list)

    def get(self, title: str, year: int | None) -> Fact:
        self.asked.append((title, year))
        return Fact(runtime=self.runtime)


class _Noted(Silent):
    """Молчащая лента, которая помнит, чем пересборка плана отчиталась о длительности."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.events.append((event, dict(fields)))


def _plan(picture: Picture) -> Any:
    return plan_for(picture, Args(query=["кино"]), Config())


def _picture() -> Picture:
    return pictures([row("Кино / Movie (1999) BDRip 1080p", "a")])[0]


def _interstellar() -> Picture:
    """Картина, у которой прикидка врёт: 2 ч 49 мин против двух часов.

    Пул нарочно из двух ступеней: честный 1080p на 16.5 ГБ, который прикидка выкидывает
    потолком, и 720p на 4 ГБ, который она оставляет единственным годным.
    """
    return pictures(
        [
            row(
                "Интерстеллар / Interstellar (2014) BDRip 1080p | D", "a", seeders=90, size_gb=16.5
            ),
            row("Интерстеллар / Interstellar (2014) WEB-DL 720p | D", "b", seeders=120, size_gb=4),
        ]
    )[0]


def test_the_real_runtime_replaces_the_guess_in_the_denominator() -> None:
    """🔴 TC-185. Чинится ЗНАМЕНАТЕЛЬ битрейта, а потолки не двигаются ни на знак."""
    picture = _picture()
    was = _plan(picture)
    facts = _Facts(_INTERSTELLAR)

    fresh = _timed(was, facts, Args(query=["кино"]), Config())

    assert facts.asked == [("Кино", 1999)], "спрашивается та же справка, что и меню"
    assert fresh.runtime == 169 * 60.0
    assert fresh.warn_mbit == was.warn_mbit, "потолок остаётся прежним"


def test_a_silent_passport_leaves_the_plan_on_the_guess() -> None:
    """Нет статьи, нет сети, картины нет в выгрузке - план остаётся тем же объектом."""
    was = _plan(_picture())

    assert _timed(was, _Facts(), Args(query=["кино"]), Config()) is was
    assert was.runtime == RUNTIME_GUESS["movie"]


def test_without_facts_at_all_nothing_is_asked() -> None:
    """Справки не было вовсе - пересобирать план не на чем."""
    was = _plan(_picture())

    assert _timed(was, None, Args(query=["кино"]), Config()) is was


def test_the_kin_of_the_old_plan_moves_into_the_fresh_one() -> None:
    """Родня нужна одной строке отказа, и терять её при пересборке нельзя."""
    was = _plan(_picture())
    was.kin = [Picture(title="Соседняя часть", year=2001)]

    fresh = _timed(was, _Facts(_INTERSTELLAR), Args(query=["кино"]), Config())

    assert fresh is not was
    assert [picture.title for picture in fresh.kin] == ["Соседняя часть"]


def test_the_reference_runtime_returns_an_honest_1080p_to_the_queue() -> None:
    """🔴 TC-185. Справка назвала 2 ч 49 мин - и 1080p, отсеянный арифметикой, снова в очереди.

    Потолок при этом не двигается ни на знак: чинится знаменатель, а не порог.
    """
    picture = _interstellar()
    args = Args(query=["интерстеллар"])
    config = Config(recode=False)  # потолок отбора - ровно bitrate_warn_mbit
    blind = plan_for(picture, args, config)
    assert blind.candidates(args) == [1], "по прикидке годен только 720p"
    small = blind.ranked[0]

    fresh = _timed(blind, _Facts(_INTERSTELLAR), args, config)

    assert fresh.warn_mbit == blind.warn_mbit, "чинится знаменатель, а не потолок"
    assert fresh.ranked[0] is not small, "живой 1080p вернулся и встал верхом"
    assert len(fresh.candidates(args)) == 2


def test_a_hand_picked_release_keeps_the_number_the_table_showed() -> None:
    """🔴 TC-216. ``--release N`` играет ровно ту раздачу, что стояла под номером N в таблице.

    Держится инвариант не заслонкой, а тем, что ОБЕ стороны считают битрейт по одной
    длительности: ``cast releases`` спрашивает справку так же, как путь показа. Пока
    таблица строилась на прикидке, порядок сходился ценой вранья про битрейт.
    """
    picture = _interstellar()
    config = Config(recode=False)
    asked = Args(query=["интерстеллар"])
    by_hand = Args(query=["интерстеллар"], release=2)

    shown = _timed(plan_for(picture, asked, config), _Facts(_INTERSTELLAR), asked, config)
    played = _timed(plan_for(picture, by_hand, config), _Facts(_INTERSTELLAR), by_hand, config)

    assert [r.raw_name for r in played.ranked] == [r.raw_name for r in shown.ranked], (
        "номер из таблицы означает ту же раздачу на показе"
    )
    assert played.runtime == shown.runtime, "длительность у таблицы и у показа одна"


def test_a_silent_passport_says_so_in_the_trace_and_does_not_keep_quiet() -> None:
    """Справка молчит - план остаётся на прикидке, и это видно в следе, а не молча.

    Молчание тут - обычное дело (нет статьи, нет сети, картины нет в выгрузке), и цена
    его - заниженный знаменатель битрейта у каждого длинного фильма. Не назови след
    источник длительности, разбирать такие показы было бы нечем.
    """
    was = _plan(_picture())
    noted = _Noted()
    install(noted)
    try:
        assert _timed(was, _Facts(), Args(query=["кино"]), Config()) is was
    finally:
        install(Silent())

    runtime = [fields for event, fields in noted.events if event == "runtime"]
    assert runtime and runtime[-1]["src"] == "guess"
    assert runtime[-1]["secs"] == round(RUNTIME_GUESS["movie"])


def test_the_count_of_the_late_survives_the_rebuild_on_the_real_runtime() -> None:
    """🔴 TC-703. Справка пересобирает план, а признак неполноты каталога нужен позже него."""
    install(_Noted())
    plan = _plan(_interstellar())
    plan.waiting = lambda: ("JacRed",)

    fresh = _timed(plan, _Facts(_INTERSTELLAR), Args(query=["кино"]), Config())

    assert fresh is not plan, "справка собрала новый план"
    assert fresh.waiting() == ("JacRed",)


def test_the_memory_of_the_studio_survives_the_rebuild_on_the_real_runtime() -> None:
    """🔴 TC-701. Справка пересобирает план, а память студии решает его порядок.

    Пересборка идёт после меню и до показа, и потеряй она студию тут - порядок молча
    вернулся бы к лотерее ровно там, где человек её и не ждёт.
    """
    install(_Noted())
    plan = _plan(_interstellar())
    plan.studio = "LostFilm"

    fresh = _timed(plan, _Facts(_INTERSTELLAR), Args(query=["кино"]), Config())

    assert fresh is not plan, "справка собрала новый план"
    assert fresh.studio == "LostFilm"
