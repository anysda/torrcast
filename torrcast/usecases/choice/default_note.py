"""Одна честная строка про смену картины: спросили X - беру Y, потому что Z."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.first_alive import _first_alive
from torrcast.usecases.choice.fitness import fitness
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.ports.choice_types import _Plan


def default_note(plans: list[_Plan], asked: str = "") -> str:
    """🔴 TC-198. Одна честная строка про смену картины: «спросили X - беру Y, потому что Z».

    Молчаливая подмена КАРТИНЫ - худший вид брака, а дефолт франшизы подменяет её
    буднично: пропускает мёртвую первую часть (:func:`alive_numbers`), уходит с
    однораздачной (:func:`backed`), считается среди сериалов (:func:`asked_kind`) - и
    всё это без единого слова. В замере каталога так молча прошли десять спорных
    запросов из четырнадцати: «мумия» показывала не ту «Мумию», «дюна» - не ту «Дюну»,
    «медведь s2e7» - не тот «Медведь». Ещё у четырёх строка была, но про другое: у
    «гарри поттера» человек читал про оригинальное имя и добор сезона, пока менялась
    ЧАСТЬ франшизы.

    Строка одна, и печатается она **последней перед стартом** (:func:`_cmd_play`), а не
    среди фаз поиска: фазы уезжают вверх экрана и читаются как ход работы, а это -
    решение, которое человек обязан унести с собой.

    Пусто - взято ровно то, что назвали, и говорить не о чем. Три случая молчания
    осознанные:

    * картина одна - выбора не было вовсе;
    * человек ответил на меню сам - подмены нет, есть его выбор (сравнение с
      :func:`first_alive` делает вызывающий);
    * дефолт сел на картину, чьё имя человек и назвал, а тёзок по году у неё нет:
      «голодные игры» → «Голодные игры» (2012) - это ровно запрошенное, и строка тут
      была бы шумом. Ровно это и чинит TC-196: после него три случая из четырнадцати
      перестают быть сменой вообще.

    ``asked`` - слова человека; без них строка та же, только без головы «спросили X».
    """
    numbers = asked_kind(plans)
    picked = _first_alive(plans, numbers)
    plain = _first_alive(plans, list(range(1, len(plans) + 1)))
    head = f"спросили «{asked}» - беру" if asked else "беру"
    mine = _named(plans[picked - 1].picture)
    if len(numbers) != len(plans) and picked != plain:
        other = _named(plans[plain - 1].picture)
        return f"{head} «{mine}», а не «{other}»: спросили серию, а это другой тип"
    if passed := [n for n in numbers if n < picked]:
        other = _named(plans[passed[0] - 1].picture)
        return f"{head} «{mine}», а не «{other}»: {_passed_why(plans, passed[0], numbers)}"
    if twins := [n for n in numbers if n != picked and _namesake(plans, n, picked)]:
        others = ", ".join(f"«{_named(plans[n - 1].picture)}»" for n in twins)
        return f"{head} «{mine}»: под этим именем есть ещё {others} - другая картина"
    return ""


def _passed_why(plans: list[_Plan], number: int, numbers: list[int]) -> str:
    """Почему картина, стоящая раньше по хронологии, дефолтом не стала.

    Причины ровно четыре, и человеку они разные: «играть нечем» (годной раздачи нет ни
    одной - образы дисков, 4K сверх потолка декодера, старьё), «рой мёртв» (годная
    раздача есть, но сидов у неё столько, что это подгрузы), «живого HD нет»
    (:func:`playable`: у тёзки того же имени он есть, а тут одно старьё) и «всего одна
    раздача» (:func:`backed`: одно обещание индексера против очереди у соседки).
    """
    life = liveliness(plans[number - 1])
    if life <= 0:
        return "играть у неё нечем - ни одной годной раздачи"
    if number not in alive_numbers(plans, numbers):
        return f"рой у неё мёртв - сидов {life}"
    if not fitness(plans[number - 1]):
        return "живого HD у неё нет - одно старьё"
    return f"у неё всего одна раздача, а тут их {len(plans[number - 1].ranked)}"
