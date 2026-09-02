"""Номер сериала, когда под одним именем нашлись и фильм, и сериал; 0 - не случай."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def series_take(plans: list[Plan]) -> int:
    """Номер (с единицы) самого живого сериала выдачи; 0 - вид тут ничего не решает.

    Решение владельца 02-09-2026: «без меню между фильмом и сериалом выбирать сериал».
    «Байки Мэтра» - мультсериал 2008-2012, а дефолтом вставала одноимённая нарезка
    короткометражек: вид картины в выборе не весил ничего, пока запрос не назвал серию
    (:func:`asked_kind`).

    🔴 Вторая половина того же решения важнее первой: «если я пишу тачки он не должен
    выбрать тачки байки мэтра». Предпочтение вида не имеет права утащить выбор у
    запроса, который сериала не звал, и держат его тут два ограждения:

    * **франшиза молчит целиком.** Есть в выдаче хоть одна картина с номером части -
      правило не работает вовсе. Замер по живой выдаче: «рэмбо» даёт 13 картин, среди
      них сериал-тёзка «РэмбО» 2022 года на 16 раздач и 89 сид против «Первой крови»
      1982 года на 74, - живее оказывается сериал, и без этого ограждения Enter уезжал
      бы с «Первой крови» на него. Номер части несут «Рэмбо: Первая кровь 2», «Рэмбо 3»,
      «Рэмбо IV» - и правило молчит. Так же молчит «тачки» («Тачки 2», «Тачки 3»);
    * **мёртвый сериал не берётся.** Живого сериала нет - вид не повод менять картину:
      уводить с живого фильма на пустой рой хуже, чем не слушать вид вовсе.

    Дефолт сам сериал - возвращается 0: менять нечего, и лишняя строка была бы шумом.
    Сериалы вся выдача - тоже 0: между ними вид не спорит, там решает живость.

    Вид спрашивается у :attr:`~torrcast.usecases.select.plan.Plan.selection_kind` - то
    есть тот, который видел ВЫБОР: метаданные выбранной раздачи уточняют
    :attr:`Picture.kind` позже, и пересчитывать по ним уже сделанный выбор нельзя.
    """
    if any(plan.picture.part is not None for plan in plans if plan.picture.kind != "other"):
        return 0
    series = [n for n, plan in enumerate(plans, start=1) if plan.selection_kind == "tv"]
    if not series or len(series) == len(plans) or first_alive(plans) in series:
        return 0
    alive = alive_numbers(plans, series)
    if not alive:
        return 0
    return max(alive, key=lambda n: (liveliness(plans[n - 1]), -n))


__all__ = ["series_take"]
