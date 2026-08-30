"""Зеркало :mod:`torrcast.usecases.choice.enter_take`: кого включит Enter.

Ступень одна на всех, кто спрашивает этот вопрос: и прогрев под меню, и сам вопрос
читают её приговор, а своего мнения не имеют. Поэтому тут мерится не «что напечатали»,
а ровно номер и правило, которым он взят.
"""

from __future__ import annotations

import pytest

from tests.usecases.choice.branches import Branch, branches
from tests.usecases.choice.world import parts
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
    if branch.refuses:
        assert take.refusal, "ветка отказа обязана назвать причину"
        assert not take.takes
    elif branch.takes:
        assert take.takes, "Enter берёт картину - значит у вопроса есть дефолт"
        assert take.number == branch.takes
    else:
        assert not take.takes, "номер зовёт человек - дефолта у вопроса нет"
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
