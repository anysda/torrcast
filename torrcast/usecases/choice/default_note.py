"""Одна честная строка про смену картины: спросили X - беру Y, потому что Z."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice._namesake import _namesake
from torrcast.usecases.choice.alive_numbers import alive_numbers
from torrcast.usecases.choice.asked_kind import asked_kind
from torrcast.usecases.choice.asked_season_number import asked_season_number
from torrcast.usecases.choice.carries_season import carries_season
from torrcast.usecases.choice.first_alive import _first_alive, first_alive
from torrcast.usecases.choice.fitness import fitness
from torrcast.usecases.choice.liveliness import liveliness

if TYPE_CHECKING:
    from torrcast.usecases.select.plan import Plan


def default_note(plans: list[Plan], asked: str = "") -> str:
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

    🔴 TC-860. Молчание было и четвёртым, не осознанным: вся ветка про пропущенную
    часть выше стоит под условием «дефолт не первый пункт» - а решение о сезоне
    (:func:`~torrcast.usecases.choice.asked_season.asked_season`) молча принимается и
    тогда, когда дефолт как раз первый. Меню из «Мираж 2» и «Мираж 3» на просьбу первого
    сезона: ни одна не несёт его - ни частью, ни именем раздачи, - узкие ворота
    отступают к «считаем как считали», и дефолтом молча встаёт часть 2. Первым пунктом
    меню она стоит по хронологии - но зрителю нужен был сезон, которого в выдаче не
    было вовсе, и об этом обязана сказать та же строка.
    """
    numbers = asked_kind(plans)
    picked = first_alive(plans)
    plain = _first_alive(plans, list(range(1, len(plans) + 1)))
    head = f"спросили «{asked}» - беру" if asked else "беру"
    mine = _named(plans[picked - 1].picture)
    if picked > 1:
        other = _named(plans[0].picture)
        why = (
            "спросили серию, а это другой тип"
            if 1 not in numbers
            else _passed_why(plans, 1, numbers)
        )
        return f"{head} «{mine}», а не «{other}»{f': {why}' if why else ''}"
    if len(numbers) != len(plans) and picked != plain:
        other = _named(plans[plain - 1].picture)
        return f"{head} «{mine}», а не «{other}»: спросили серию, а это другой тип"
    if twins := [n for n in numbers if n != picked and _namesake(plans, n, picked)]:
        others = ", ".join(f"«{_named(plans[n - 1].picture)}»" for n in twins)
        return f"{head} «{mine}»: под этим именем есть ещё {others} - другая картина"
    season = asked_season_number(plans)
    picture = plans[picked - 1].picture
    if season is not None and not carries_season(picture, season):
        part = picture.part
        return f"{head} «{mine}»: спрошен {season} сезон, а в выдаче его нет - у неё часть {part}"
    return ""


def _passed_why(plans: list[Plan], number: int, numbers: list[int]) -> str:
    """Почему картина, стоящая раньше по хронологии, дефолтом не стала.

    Причины ровно четыре, и человеку они разные: «играть нечем» (годной раздачи нет ни
    одной - образы дисков, 4K сверх потолка декодера, старьё), «рой мёртв» (годная
    раздача есть, но сидов у неё столько, что это подгрузы), «живого HD нет»
    (:func:`playable`: у тёзки того же имени он есть, а тут одно старьё) и «всего одна
    раздача» (:func:`backed`: одно обещание индексера против очереди у соседки).

    Счёт раздач в последней причине - у ВЗЯТОЙ картины (:func:`first_alive`), ради
    которой пропуск и объясняется. У взятой тоже одна раздача - сравнивать нечего, и
    причина молчит: строка, которая врёт про причину выбора, хуже отсутствия строки.
    """
    life = liveliness(plans[number - 1])
    if life <= 0:
        return "играть у неё нечем - ни одной годной раздачи"
    if number not in alive_numbers(plans, numbers):
        return f"рой у неё мёртв - сидов {life}"
    if not fitness(plans[number - 1]):
        return "живого HD у неё нет - одно старьё"
    taken = len(plans[first_alive(plans) - 1].ranked)
    if taken <= 1:
        return ""
    return f"у неё всего одна раздача, а тут их {taken}"
