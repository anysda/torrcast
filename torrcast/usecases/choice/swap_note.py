"""Честная строка про смену картины для того, что реально пошло на показ."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice.default_note import default_note
from torrcast.usecases.choice.first_alive import first_alive

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def swap_note(plans: list[Plan], picked: Plan, asked: str = "") -> str:
    """Честная строка про смену картины для ТОГО, что реально пошло на показ.

    От :func:`default_note` отличается одним вопросом: а дефолт ли это. Человек, который
    ответил на меню номером, ничего не подменял - он выбрал, и говорить ему «беру не то,
    что вы назвали» было бы враньём. Поэтому строка живёт ровно там, где картину выбрали
    за него: выбранный пункт совпал с дефолтом (:func:`first_alive`).

    Картина одна - меню не задавалось вовсе, выбора не было, и строки нет.
    """
    if not _is_default(plans, picked):
        return ""
    return default_note(plans, asked)


def _is_default(plans: list[Plan], picked: Plan) -> bool:
    """Встал ли выбранный план дефолтом (:func:`first_alive`), а не выбором человека.

    Человек, ответивший на меню номером, ничего не подменял - он выбрал. Строки про
    подмену (:func:`swap_note`, :func:`year_note`) живут ровно там, где картину выбрали
    за него. Картина одна - меню не задавалось вовсе, выбора не было.

    План после меню пересобирается на настоящей длительности (:func:`_timed`) и это уже
    ДРУГОЙ объект - сверка идёт по картине, идентичность тут врёт.
    """
    if len(plans) < 2:
        return False
    number = next((n for n, plan in enumerate(plans, start=1) if plan.picture is picked.picture), 0)
    return number == first_alive(plans)
