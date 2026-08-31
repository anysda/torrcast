"""Дописывание справки в уже показанные строки меню."""

from __future__ import annotations

from itertools import accumulate
from typing import TYPE_CHECKING

from torrcast.domain.outside_numbering import outside_numbering
from torrcast.usecases.choice.head_line import head_line

if TYPE_CHECKING:
    from torrcast.ports.menu_paint import MenuPaint
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select.plan import Plan


def _dress(menu: MenuPaint, plans: list[Plan], blocks: list[list[str]], facts: Facts) -> None:
    """Подписать показанное меню на справку: приехавшее дописывается в стоящую строку.

    🔴 Решение владельца: рейтинг дописывается в уже показанную строку - зритель видит, как
    она дополняется, и не ждёт её. Ждать ВСЮ справку меню не вправе: ждали её полторы
    секунды, и в две трети прогонов она в них не укладывалась, то есть человек платил
    ожиданием и всё равно получал голый список. Из неё меню ждёт только описание (TC-717) -
    ровно то, чего эта единица дописать не умеет.

    Строка собирается тем же :func:`head_line`, что и при первой печати, и переписывается
    только когда стала ДРУГОЙ: пустой звонок не должен мигать экраном. Место строки
    считается по кускам меню - у картины с описанием их несколько, и без этого счёта
    рейтинг лёг бы в чужой пункт.

    🔴 Справка спрашивается ВНУТРЕННИМ именем картины - тем же, каким её заказали
    (:func:`~torrcast.usecases.cast_command._choose._choose`) и каким её читает первая
    печать (:func:`~torrcast.usecases.choice.menu_blocks.menu_blocks`). Спроси её именем
    с экрана - под английским языком ключ разошёлся бы с заказанным, ответом на каждый
    пункт стала бы пустая справка, и дописывание СТИРАЛО бы уже показанные рейтинг,
    хронометраж и описание: строка «дополнялась» бы до голой.

    Описание тут не дописывается намеренно, и это не цена, а граница: оно занимает не одну
    строку, а несколько, и вставить их в середину уже прочитанного списка нельзя - список
    поехал бы под курсором у человека, который его в эту секунду читает. Поэтому описание
    ждут ДО печати (:meth:`~torrcast.usecases.facts.Facts.wait_about`), а опоздавшее и там
    попадает в кэш (:meth:`~torrcast.usecases.facts.Facts.finish`), и следующее меню печатает
    его сразу.
    """
    aside = outside_numbering([plan.picture for plan in plans])
    heads = list(accumulate((len(block) for block in blocks), initial=0))
    shown = [block[0] for block in blocks]

    def dress() -> None:
        for at, plan in enumerate(plans):
            picture = plan.picture
            fact = facts.ready(picture.title, picture.year)
            line = head_line(at + 1, picture, fact, picture.key in aside)
            if line != shown[at]:
                shown[at] = line
                menu.redraw(heads[at], line)

    facts.watch(dress)
    # Между печатью списка и этой подпиской справка успевает приехать - и без догоняющего
    # звонка меню осталось бы голым при готовой справке на руках.
    dress()
