"""Вопрос «Что смотрим?» и выбор картины меню."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.choice_environment import ChoiceEnvironment
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.menu_lines import menu_lines
from torrcast.usecases.choice.part_one_swap import part_one_swap

if TYPE_CHECKING:
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select._plan import _Plan


def _pick_plan(
    plans: list[_Plan],
    facts: Facts | None = None,
    pick: int | None = None,
    asked: str = "",
    environment: ChoiceEnvironment | None = None,
) -> _Plan:
    """Вопрос «какой фильм франшизы?»; один вариант — без вопроса.

    Дефолт — верхняя картина меню. Если играть её нечем, отбор называет причину и не
    подставляет соседнюю картину.

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

    Без терминала (ssh без pty, cron, чужой скрипт) спрашивать некого, и общее правило —
    не висеть, а брать дефолт. Здесь мы по-прежнему отказываемся — и «дефолт стал умнее»
    ничего не меняет. У озвучки дефолт считается правилами, а продолжение и вовсе
    молчит; тут же любой дефолт означает **другой фильм**: разница между «Моаной»
    2016 и «Моаной 2» — это не оттенок, а не тот вечер. Цифра в скобках имеет смысл
    ровно потому, что рядом напечатан список и человек видит, от чего отказывается;
    без терминала видеть его некому. Поэтому отказываемся вслух и подсказываем, как
    назвать картину точно.
    """
    env = environment or _environment_port()
    if pick is not None and not 1 <= pick <= len(plans):
        raise env.not_found_error(f"подходит картин: {len(plans)}, номера {pick} нет")
    env.write(menu_lines(plans, facts))
    if pick is not None:  # номер назвал сам человек - ни вопроса, ни подмены
        return plans[pick - 1]
    if len(plans) == 1:
        return plans[0]
    default = 1
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
