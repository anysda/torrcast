"""Зеркало :mod:`torrcast.usecases.choice.enter_take`: кого включит Enter.

Ступень одна на всех, кто спрашивает этот вопрос: и прогрев под меню, и сам вопрос
читают её приговор, а своего мнения не имеют. Поэтому тут мерится не «что напечатали»,
а ровно номер и правило, которым он взят.
"""

from __future__ import annotations

import pytest

from tests.usecases.choice.branches import Branch, branches
from tests.usecases.choice.world import Outside, outside, parts, plan
from torrcast.usecases.choice.enter_take import enter_take


@pytest.mark.parametrize("branch", branches(), ids=lambda one: one.why)
def test_each_rule_names_its_number_and_names_itself(branch: Branch) -> None:
    """Каждое правило берёт свой номер и подписывается своим именем.

    Имя правила уезжает в журнал замера рядом с отметкой о пуске прогрева (TC-108): без
    него в разборе видно, ЧТО грелось, но не видно, почему грелось именно это.
    """
    menu = branch.menu()

    take = enter_take(menu, branch.asked, branch.pick, branch.flag)

    assert take.why == branch.why
    # Номер есть у ЛЮБОГО приговора, даже когда Enter не берёт ничего: греть кого-то
    # под меню всё равно надо, и целиться прогреву больше не во что.
    assert 1 <= take.number <= len(menu), "приговор обязан назвать картину для прогрева"
    if branch.takes:
        assert take.takes, "Enter берёт картину - значит у вопроса есть дефолт"
        assert take.number == branch.takes
    else:
        assert not take.takes, "за явным меню номер зовёт человек"
        assert take.asks, "без дефолта вопрос обязан подняться со списком"


def test_a_number_outside_the_menu_is_not_taken_here() -> None:
    """Номер вне списка ступень не берёт: его завернёт честной ошибкой сам вопрос.

    Возьми она его - прогрев полез бы за край списка ещё до того, как человек услышал
    бы про ошибку.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    take = enter_take(mummy, "мумия", pick=9)

    assert take.why != "номер флагом"
    assert 1 <= take.number <= len(mummy)


def test_a_series_that_renames_the_picture_does_not_take_it_over() -> None:
    """Боевой проводкой: спинофф с лишними словами в имени картину у саги не забирает.

    Дефолт тут не первый номер, поэтому :func:`certain_default` молчит и очередь доходит
    до правила вида, - ровно тот расклад, на котором продукт 05-09-2026 отдавал человеку
    «Дарт Мол: Повелитель теней» на запрос «звездные войны».
    """
    saga = [
        plan("Звёздные войны: Эпизод II - Атака клонов", 2002, seeders=1),
        plan("Звёздные войны: Эпизод I - Скрытая угроза", 1999, seeders=300),
        plan("Звёздные войны. Дарт Мол: Повелитель теней", 2026, kind="tv", seeders=90),
    ]

    with outside(Outside()):
        take = enter_take(saga, "звездные войны")

    assert take.number == 2, "вид не повод менять картину на другую"
    assert saga[take.number - 1].picture.title == "Звёздные войны: Эпизод I - Скрытая угроза"
