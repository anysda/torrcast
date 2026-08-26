"""Печать списка картин меню: с ожиданием справки или с дописыванием её курсором."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._dress import _dress
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.menu_blocks import menu_blocks

if TYPE_CHECKING:
    from torrcast.ports.choice_environment.choice_environment import ChoiceEnvironment
    from torrcast.ports.menu_paint import MenuPaint
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select.plan import Plan


def _shown(
    env: ChoiceEnvironment, plans: list[Plan], facts: Facts | None, dress: bool, asked: str
) -> MenuPaint:
    """Напечатать список; ``dress`` - дописывать ли в него приезжающую справку.

    Дописывать её есть смысл ровно там, где человек смотрит на список и отвечает: строка
    дополняется у него на глазах. Где вопроса не будет вовсе или вывод ушёл не на экран
    (труба, файл, юнит), переписать напечатанное уже нечем - там справку ждут, как ждали:
    лучше подождать полторы секунды и напечатать со справкой, чем напечатать голое навсегда.

    Показанный порядок запоминается тем же словом, что и таблица ``cast releases``
    (:meth:`ChoiceEnvironment.remember_pick`): номер пункта - адрес, и под ним в следующем
    запуске обязана стоять ТА картина, что стояла при показе списка.
    """
    menu = env.menu()
    dress = dress and menu.live and facts is not None
    if facts is not None and not dress:
        facts.wait()
    blocks = menu_blocks(plans, facts)
    menu.show([line for block in blocks for line in block])
    env.remember_pick(asked, [(p.picture.key, _named(p.picture)) for p in plans])
    if dress and facts is not None:
        _dress(menu, plans, blocks, facts)
    return menu
