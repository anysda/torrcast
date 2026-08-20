"""Вопрос «Что смотрим?» и выбор картины меню."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.choice_environment.choice_environment import ChoiceEnvironment
from torrcast.usecases.choice.certain_default import certain_default
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.menu_lines import menu_lines
from torrcast.usecases.choice.part_one_swap import part_one_swap
from torrcast.usecases.choice.taken_line import taken_line

if TYPE_CHECKING:
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select.plan import Plan


def _pick_plan(
    plans: list[Plan],
    facts: Facts | None = None,
    pick: int | None = None,
    asked: str = "",
    environment: ChoiceEnvironment | None = None,
) -> Plan:
    """Вопрос «какой фильм франшизы?» - и только там, где спрашивать есть о чём.

    🔴 Дефолт у прибора ОДИН - :func:`first_alive`, и это та же картина, о которой
    говорят честные строки про смену (:func:`default_note`, :func:`swap_note`,
    :func:`year_note`, :func:`part_one_swap`). Пока Enter брал верх меню, а строки
    считали дефолт своей меркой, эти двое расходились на 23 запросах из 71, и на всех
    23 строка молчала: она сверялась с одной картиной, а печаталась про другую, поэтому
    сказать ей было нечего. Человек жал Enter и получал «Титаник» 1943 года вместо
    1997-го, фильм «Фарго» вместо третьего сезона, «Медведя» 1938 года вместо седьмой
    серии - и ни слова о том, что картина другая. Замер по эталонной разметке того же
    корпуса: из 23 расхождений первая живая права на 16, верх меню - на одном, на одном
    неправы обе, на пяти разметка тёзок по году не различает.

    🔴 Несколько подошедших картин - ещё не повод спрашивать. Вопрос остаётся там, где
    о выборе есть что сказать честной строкой; где сказать нечего (:func:`certain_default`),
    верх меню и есть спрошенная картина, и показ начинается сам. Молчаливым это решение
    не бывает: :func:`taken_line` называет взятую картину, число подошедших и ход к
    любой другой. Терминал такому пути не нужен вовсе - ни висеть, ни отказываться тут
    не на чем.

    🔴 TC-373. Ограждение того же дефолта: перескочив через спрошенную часть франшизы
    (её нет в выдаче или играть ей нечем), он вставал на ДРУГУЮ часть - и Enter включал
    «Тачки 2» вместо просимых «Тачек». Такому дефолту не бывать (:func:`part_one_swap`):
    строка говорит, что случилось с первой частью, список остаётся на экране, и номер
    называет сам человек.

    К каждой картине печатается справка (:mod:`torrcast.runtime.facts_wiring`) — рейтинг, хронометраж
    и фраза о том, что это за кино. Её тут не ждут: что успело приехать фоном, то и печатается,
    остальное просто не печатается.

    ``pick`` - номер пункта, названный флагом ``--pick N``: вопрос тогда не задаётся
    вовсе, и терминал не нужен. Это не молчаливая подмена, а названный человеком выбор -
    тот же номер, что стоит у пункта меню на экране. Номер вне списка - честная ошибка,
    а не тихий первый пункт.

    Спрашивать есть о чём, а терминала нет (ssh без pty, cron, чужой скрипт) - тут мы
    по-прежнему отказываемся. Любой дефолт означает в этом месте **другой фильм**:
    разница между «Моаной» 2016 и «Моаной 2» — это не оттенок, а не тот вечер. Цифра в
    скобках имеет смысл ровно потому, что рядом напечатан список и человек видит, от чего
    отказывается; без терминала видеть его некому. Поэтому отказываемся вслух и
    подсказываем, как назвать картину точно.
    """
    env = environment or _environment_port()
    if pick is not None and not 1 <= pick <= len(plans):
        raise env.not_found_error(f"подходит картин: {len(plans)}, номера {pick} нет")
    if pick is not None:  # номер назвал сам человек - ни вопроса, ни подмены
        env.write(menu_lines(plans, facts))
        return plans[pick - 1]
    if len(plans) == 1:
        return plans[0]
    default = first_alive(plans)
    if certain_default(plans, asked):
        env.write(taken_line(plans, default, asked))
        return plans[default - 1]
    env.write(menu_lines(plans, facts))
    if not env.stdin_is_tty():
        raise env.not_found_error(
            f"подходит картин: {len(plans)}, а терминала нет - вслепую не выбираю; "
            f"назови картину точно (например «{plans[default - 1].picture.title}») "
            f"или её номер (--pick N), либо запусти cast в терминале"
        )
    if note := part_one_swap(plans, asked):
        # Дефолт подменил бы спрошенную часть другой - тогда его нет вовсе: строка
        # называет, что с первой частью, список на экране, номер зовёт человек.
        env.write(note)
        return plans[env.ask("Что смотрим?", len(plans), default=None) - 1]
    env.write(default_line(plans, default))
    return plans[env.ask("Что смотрим?", len(plans), default=default) - 1]
