"""Шов TC-829: греется та картина, которую включит Enter, и разойтись им нечем.

Зеркало ходит боевым путём целиком - настоящая ступень взятия, настоящий вопрос,
настоящий прогрев, - и смотрит на стенд отбора: кому досталась голова прогрева и кому
достался запасной релиз. Подделан ровно ввод-вывод пульта и справка; правила отбора,
живости и стражи работают боевые.

Пересказывать правила взятия тут нельзя намеренно: пересказ и есть тот самый шов, ради
которого зеркало заведено, - две редакции одного решения расходятся молча.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any, cast

import pytest

from tests.fakes import composition
from tests.usecases.choice.branches import Branch, branches
from tests.usecases.choice.world import Outside, outside
from torrcast.domain.args import Args
from torrcast.domain.catalogs.tongue import RU, _choose_tongue
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.facts.fact import Fact
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.choice import enter_take as enter_take_module
from torrcast.usecases.choice._passport import _Passport
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.start_clock import _Clock


class _Facts:
    """Справка, которой нечего сказать: зеркало меряет прогрев, а не рейтинги."""

    def __init__(self, wanted: object) -> None:
        self.wanted = wanted

    def start(self) -> None:
        return None

    def finish(self) -> None:
        return None

    def wait(self) -> None:
        return None

    def wait_about(self) -> None:
        return None

    def watch(self, dress: object) -> None:
        return None

    def ready(self, title: str, year: int | None) -> Fact:
        return Fact()

    def get(self, *_rest: object) -> Fact:
        return Fact()


@pytest.fixture(autouse=True)
def _russian_catalog() -> None:
    """Русские ожидания этого зеркала явно выбирают русский каталог."""
    _choose_tongue(RU)


class _NoPassport:
    def get(self) -> Any:
        from torrcast.domain.facts.origin import Origin

        return Origin()


class _WatchBench:
    """Стенд под наблюдением: кого попросили греть и кому достался запасной релиз."""

    def __init__(self) -> None:
        self.warmed: list[str] = []
        self.spared: list[str] = []
        self.dropped = False

    def start(self, plan: Plan, number: int) -> None:
        self.warmed.append(plan.picture.key)

    def spare(self, plan: Plan, args: object) -> list[object]:
        self.spared.append(plan.picture.key)
        return []

    def drop_all(self) -> None:
        self.dropped = True


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Справка и служба раздач - подделкой от корня: сеть и рой за ними не стоят."""
    composition.use_facts(monkeypatch, _Facts)
    composition.use_engines(monkeypatch, lambda url, timeout=30.0: object())


def _walked(branch: Branch, world: Outside) -> tuple[list[Plan], Plan | None, _WatchBench]:
    """Пройти боевой путь до вопроса и вернуть меню, взятую картину и стенд.

    Закладка отвечает КОДОМ сразу после вопроса: к этой секунде прогрев уже пущен и
    запасной релиз уже роздан - ровно то, что зеркало и смотрит.
    """
    menu = branch.menu()
    bench = _WatchBench()
    taken: list[Plan] = []

    def bookmark(config: object, state: object, plan: Plan, stand: object, **rest: object) -> int:
        taken.append(plan)
        return EXIT_OK

    args = Args(query=branch.asked.split(), pick=branch.pick, menu=branch.flag)
    with outside(world):
        _choose(
            Config(),
            cast(Any, args),
            Choice(profile=CAUTIOUS, how="стенд"),
            WatchState(),
            None,
            _Clock(),
            circle=lambda *rest, **named: menu,
            stand=lambda *rest, **named: cast(Bench, bench),
            passport_of=lambda pictures: cast(_Passport, _NoPassport()),
            bookmark=bookmark,
        )
    return menu, (taken[0] if taken else None), bench


@pytest.mark.parametrize("branch", branches(), ids=lambda one: one.why)
def test_the_warm_and_the_take_cannot_disagree(branch: Branch) -> None:
    """🔴 По КАЖДОМУ правилу взятия запасной релиз достаётся ровно той картине, что пошла.

    Запасной релиз - самое дорогое, что раздаёт прогрев: это вторая раздача картины,
    поднятая заранее на случай брака верха. Уйдёт он соседке - зритель, нажавший Enter,
    платит подъёмом роя с нуля, 6-7 секунд чёрного экрана, а на молчащем рое и того
    больше. На корпусе ``pools-both.jsonl`` до правки так расходились 10 запросов из 74.

    Там, где Enter не берёт ничего (страж первой части, названное мимо дефолта), сверять
    нечего по существу: номер называет человек, и целиться прогреву не во что, кроме
    дефолта франшизы. Зеркало и утверждает ровно это - вопрос поднят БЕЗ дефолта.
    """
    world = Outside(answers=[branch.answer] if branch.answer is not None else [])

    if branch.refuses:
        with pytest.raises(NotFoundError):
            _walked(branch, world)
        return

    menu, taken, bench = _walked(branch, world)

    assert taken is not None, "вопрос обязан был кончиться картиной"
    if branch.takes:
        assert bench.spared == [taken.picture.key], "запасной релиз ушёл не той картине"
        assert bench.warmed[:1] == [taken.picture.key], "голова прогрева не та картина"
    else:
        assert world.asked[-1][2] is None, "Enter тут не берёт ничего - дефолта быть не должно"
        assert bench.spared == [menu[first_alive(menu) - 1].picture.key]


def _rules_of_the_step() -> set[str]:
    """Имена правил взятия, вычитанные из ИСХОДНИКА ступени, а не переписанные сюда руками.

    Список руками - это вторая редакция того же знания, и устаревает он молча: правило
    добавили, список забыли, зеркало проехало. Ветка подписывается именем в самом коде
    (``why=``), и читается тут ровно эта подпись.
    """
    tree = ast.parse(inspect.getsource(enter_take_module))
    named: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.keyword) or node.arg != "why":
            continue
        word = node.value
        if isinstance(word, ast.Constant) and isinstance(word.value, str):
            named.add(word.value)
    return named


def test_every_rule_of_taking_is_walked_by_this_mirror() -> None:
    """🔴 Замок шва: правило, которое никто не свёл с прогревом, роняет зеркало.

    Правил взятия десять, и все они называют номер, в который целится прогрев. Появится
    одиннадцатое - тут не станет для него меню, и зеркало скажет об этом вслух, вместо
    того чтобы проехать по девяти старым и промолчать про новое.
    """
    rules = _rules_of_the_step()

    assert rules, "имена правил обязаны читаться из ступени, иначе замок пуст"
    assert {branch.why for branch in branches()} == rules


def test_the_list_on_screen_stays_chronological_when_the_warm_starts_from_the_middle() -> None:
    """Порядок списка на экране не двигается прогревом: номер - адрес, и адрес постоянен.

    Верх меню - мёртвая документалка с другим именем, дефолт стоит вторым, и греется
    вторая же картина. А на экране список остаётся хронологическим и уезжает в память
    номеров ровно в том порядке, в каком его прочитал человек: переставь его под прогрев -
    и ``cast --pick 2`` в следующем заходе включил бы другое кино.
    """
    branch = next(one for one in branches() if one.why == "дефолт с вопросом")
    world = Outside()

    menu, taken, bench = _walked(branch, world)

    assert world.said[0].splitlines() == [
        "  1. Моана: романтика золотого века (1926)",
        "  2. Моана (2016)",
        "  3. Моана 2 (2024)",
    ]
    remembered = [key for key, _named in world.remembered[-1][1]]
    assert remembered == [one.picture.key for one in menu], "порядок номеров поехал"
    assert bench.warmed[0] == menu[1].picture.key, "греется дефолт, а он второй в списке"
    assert taken is not None and taken.picture.year == 2016
