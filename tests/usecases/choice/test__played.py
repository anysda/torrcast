"""Зеркало :mod:`torrcast.usecases.choice._played`: отбор релиза с уходом к дублёру.

🔴 TC-203. Уход к тёзке - смена КАРТИНЫ, и смена эта обязана быть проверяемой отдельно от
всего пути показа: печатается строка, пишется след, план подменяется целиком.
"""

from __future__ import annotations

import pytest

import torrcast.usecases.choice._played as played_module
from tests.usecases.choice.world import Outside, outside, parts, plan
from tests.usecases.rank.releases import media, track
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.quiet import Quiet
from torrcast.usecases.choice._played import _played
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench

REFUSAL = (
    "годного релиза нет (1 - тяжёлый): выбери руками - cast releases <запрос>"
    "\nв каталоге есть Человек-невидимка (2020) - cast человек-невидимка"
)


class SwitchBench(Bench):
    """Стенд, у которого играет только картина 2020 года: 1933-я отказывает как в жизни."""

    def __init__(self) -> None:
        self.asked: list[int | None] = []
        self.kept: list[int | None] = []
        self.reordered: list[int | None] = []

    def resolve(self, plan: Plan, args: Args, progress: Progress) -> _Prep:
        self.asked.append(plan.picture.year)
        if plan.picture.year != 2020:
            raise NotFoundError(REFUSAL)
        return _Prep(number=1, release=plan.ranked[0])

    def reorder(self, before: Plan, after: Plan) -> Plan:
        self.reordered.append(before.picture.year)
        return after

    def keep_plan(self, plan: Plan) -> None:
        self.kept.append(plan.picture.year)


def invisible_man() -> list[Plan]:
    """«Человек-невидимка»: 1933 год формально жив, а играть ему нечем; 2020 - играет."""
    return parts(("Человек-невидимка", 1933, 12), ("Человек-невидимка", 2020, 140))


def test_the_show_walks_over_to_the_live_namesake_by_itself_and_says_so_out_loud() -> None:
    """Играть выбранной картиной нечем - показ уходит к живой тёзке, и это не молчком.

    Уход не безграничен: кругов ровно два - выбранная картина и одна тёзка. Дальше
    честный отказ: перебирать меню целиком дороже, чем сказать правду.
    """
    plans = invisible_man()
    bench = SwitchBench()
    world = Outside()

    with outside(world):
        played, prep = _played(
            bench,
            plans,
            plans[0],
            Args(query=["человек-невидимка"]),
            Quiet(),
            None,
            Config(),
            CAUTIOUS,
        )

    assert played.picture.year == 2020 and prep.release is plans[1].ranked[0]
    assert bench.asked == [1933, 2020], "круга ровно два"
    said = "\n".join(world.said)
    assert said.count("\n") == 0, "строка одна"
    assert "1933" in said and "2020" in said and "годного релиза нет" in said, said
    assert "cast releases" not in said, "ход руками после автоматического ухода - неправда"


def test_the_switch_leaves_a_trace_naming_both_pictures_and_the_reason() -> None:
    """След про смену картины пишется вместе со строкой: разбор потом идёт по нему."""
    plans = invisible_man()
    world = Outside()

    with outside(world):
        _played(
            SwitchBench(),
            plans,
            plans[0],
            Args(query=["человек-невидимка"]),
            Quiet(),
            None,
            Config(),
            CAUTIOUS,
        )

    event, action, facts = world.events[0]
    assert (event, action) == ("select", "switch")
    assert facts["from"] == "Человек-невидимка" and facts["to"] == "Человек-невидимка"
    assert facts["why"] == "годного релиза нет (1 - тяжёлый)"


def test_the_understudy_gets_the_same_treatment_the_menu_would_have_given_her() -> None:
    """Тёзке достаётся своя длительность из справки и свой порядок прогретого.

    Иначе она играла бы по числам выбывшей картины: чужая длительность - это чужие
    пороги битрейта и чужой порядок очереди.
    """
    plans = invisible_man()
    bench = SwitchBench()

    with outside(Outside()):
        _played(
            bench,
            plans,
            plans[0],
            Args(query=["человек-невидимка"]),
            Quiet(),
            None,
            Config(),
            CAUTIOUS,
        )

    assert bench.reordered == [2020], "порядок прогретого пересобран под новую картину"
    assert bench.kept == [2020], "прогревы чужих картин убраны уже под неё"


def test_without_a_live_namesake_the_refusal_reaches_the_person_exactly_as_it_was_born() -> None:
    """Тёзки нет - уходить некуда, и подменять отказ нечем.

    Уход к соседке по франшизе был бы подменой картины: про таких соседей отказ несёт
    подсказку сам.
    """
    cars = parts(("Тачки", 2006, 66), ("Тачки 3", 2017, 121))
    bench = SwitchBench()
    world = Outside()

    with outside(world), pytest.raises(NotFoundError, match="годного релиза нет"):
        _played(bench, cars, cars[0], Args(query=["тачки"]), Quiet(), None, Config(), CAUTIOUS)

    assert bench.asked == [2006], "лишнего круга нет"
    assert world.said == [] and world.events == [], "ухода не было - и говорить не о чем"


class VoicelessBench(SwitchBench):
    """Стенд, чей запасной ход отдаёт релиз с ЯПОНСКИМ звуком: русской дорожки нет ни у кого."""

    def __init__(self) -> None:
        super().__init__()
        self.late: list[str] = []

    def resolve(self, plan: Plan, args: Args, progress: Progress) -> _Prep:
        self.asked.append(plan.picture.year)
        if plan.picture.title == "Врата Штейна дубль":
            self.late.append(plan.picture.title)
            return _Prep(number=1, release=plan.ranked[0], media=media(tracks=(track(),)))
        return _Prep(
            number=1, release=plan.ranked[0], media=media(tracks=(track(0, "jpn", "Original"),))
        )


def _steins(brought: list[Plan] | None) -> tuple[VoicelessBench, list[str]]:
    """Отбор «Врат Штейна» с поздним кругом, отвечающим ``brought``; вернуть стенд и сказанное."""
    plans = parts(("Врата Штейна", 2011, 40))
    bench = VoicelessBench()
    world = Outside()
    late = iter(brought or [])

    def circle(*_args: object, **_kw: object) -> Plan | None:
        return next(late, None)

    with outside(world), pytest.MonkeyPatch.context() as patch:
        patch.setattr(played_module, "late_voice", circle)
        got = _played(
            bench,
            plans,
            plans[0],
            Args(query=["врата", "штейна"]),
            Quiet(),
            None,
            Config(),
            CAUTIOUS,
        )
    return bench, [got[0].picture.title]


def test_a_release_without_the_sought_voice_sends_the_show_to_the_late_circle() -> None:
    """🔴 TC-770. Запасной ход отбора отдал чужой звук - значит спрашивать ещё есть где.

    Человеку обещан показ ПО-РУССКИ, а не показ любой ценой: пул собирали по имени
    раздачи, а приговор вынес ffprobe по дорожкам, и между этими мерами лежит дыра.
    """
    bench, titles = _steins([plan("Врата Штейна дубль", 2011)])

    assert bench.late == ["Врата Штейна дубль"], "поздний круг был, и отбор по нему пошёл"
    assert titles == ["Врата Штейна дубль"], "играем добранным, а не японским"


def test_a_late_circle_that_brings_nothing_leaves_the_gathered_show_alone() -> None:
    """Круг стоит НА ПУТИ ОТКАЗА: не вышло - у человека остаётся ровно то, что было."""
    bench, titles = _steins(None)

    assert bench.late == [], "второго отбора не было"
    assert titles == ["Врата Штейна"], "прежний релиз никуда не делся"


def test_a_late_circle_that_falls_over_does_not_take_the_gathered_show_with_it() -> None:
    """🔴 Отказ позднего круга не имеет права выбрасывать уже собранное.

    Круг идёт сверх того, что человеку уже собрали и сказали. Значит любая его беда -
    молчащий индексер, отказ службы раздачи - обязана кончиться тем же, чем кончился бы
    заход без него.
    """
    plans = parts(("Врата Штейна", 2011, 40))
    bench = VoicelessBench()

    def explode(*_args: object, **_kw: object) -> Plan | None:
        raise RuntimeError("индексер лёг посреди круга")

    with outside(Outside()), pytest.MonkeyPatch.context() as patch:
        patch.setattr(played_module, "late_voice", explode)
        played, prep = _played(
            bench,
            plans,
            plans[0],
            Args(query=["врата", "штейна"]),
            Quiet(),
            None,
            Config(),
            CAUTIOUS,
        )

    assert played is plans[0] and prep.release is plans[0].ranked[0], "показ остался прежним"
    assert bench.late == [], "второго отбора не было"
