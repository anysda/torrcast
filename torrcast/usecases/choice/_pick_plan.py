"""Вопрос «Что смотрим?» и показ решения ступени взятия."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.choice_environment.choice_environment import ChoiceEnvironment
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice._shown import _shown
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.choice.take import Take

if TYPE_CHECKING:
    from torrcast.usecases.facts import Facts
    from torrcast.usecases.select.plan import Plan


def _pick_plan(
    plans: list[Plan],
    facts: Facts | None = None,
    pick: int | None = None,
    asked: str = "",
    environment: ChoiceEnvironment | None = None,
    menu: bool = False,
    take: Take | None = None,
) -> Plan:
    """Показать решение ступени взятия и спросить, если спрашивать есть о чём.

    🔴 TC-829. Кого возьмёт Enter, эта единица больше НЕ РЕШАЕТ - решает
    :func:`enter_take`, и её же приговор читает прогрев под меню
    (:func:`~torrcast.usecases.choice.warm_order.warm_order`). Здесь остаётся речь: что
    сказать, показывать ли список, спрашивать ли номер и когда отказаться. Пока решали
    оба, прогрев целился в :func:`first_alive`, а брались стражи поверх него, и на корпусе
    ``pools-both.jsonl`` эти двое расходились на 10 запросах из 74: грелась «Мумия» 1932
    года, а Enter включал 2026-ю, и зритель ждал подъёма роя с нуля.

    ``take`` - готовый приговор от того, кто уже спросил его для прогрева
    (:func:`~torrcast.usecases.cast_command._choose._choose`): один приговор на оба дела,
    и расходиться тогда нечему физически. Без него приговор спрашивается тут же - той же
    единицей и на тех же входах.

    К каждой картине печатается справка (:mod:`torrcast.runtime.facts_wiring`) — рейтинг,
    хронометраж и фраза о том, что это за кино. 🔴 Ждут из неё ровно ОПИСАНИЕ (TC-717): его
    уже не дописать в показанный список. Рейтинг и хронометраж приезжают в готовые строки
    курсором — зритель видит, как строка дополняется, и отвечает в любую секунду этого
    дописывания. Целиком справку ждём там, где дописывать её будет некому (:func:`_shown`).

    ``pick`` - номер пункта, названный флагом ``--pick N``: вопрос тогда не задаётся
    вовсе, и терминал не нужен. Номер берётся из показанного списка - таблицы
    ``cast releases`` или этого меню, - а состав выдачи гуляет от захода к заходу, поэтому
    номер сверяется с запомненным порядком
    (:meth:`ChoiceEnvironment.recalled_pick`): под ним обязана стоять ТА картина, что
    стояла при выдаче номера. Расхождение - отказ, называющий обе картины, а не показ
    соседки. Картина при этом проговаривается вслух в любом исходе - номер молчит.
    Номер вне списка - честная ошибка, а не тихий первый пункт.

    Спрашивать есть о чём, а терминала нет (ssh без pty, cron, чужой скрипт) - тут мы
    по-прежнему отказываемся: любой дефолт в этом месте - ДРУГОЙ фильм, а цифра в
    скобках имеет смысл, только когда рядом напечатан список. Отказываемся вслух и
    подсказываем, как назвать картину точно.
    """
    env = environment or _environment_port()
    if pick is not None and not 1 <= pick <= len(plans):
        raise env.not_found_error(f"подходит картин: {len(plans)}, номера {pick} нет")
    verdict = take if take is not None else enter_take(plans, asked, pick, menu)
    plan = plans[verdict.number - 1]
    if pick is not None:  # номер назвал сам человек - ни вопроса, ни подмены
        key, named = env.recalled_pick(asked, pick)
        if key and key != plan.picture.key:
            # Номер - адрес из показанной таблицы, а состав выдачи гуляет: под тем же
            # номером сегодня стоит ДРУГАЯ картина. Показать её молча - подмена; отказ
            # называет, что стояло под номером тогда и что стоит сейчас.
            raise env.not_found_error(
                f"под номером {pick} в таблице «{asked}» была «{named}», "
                f"а сейчас под ним «{_named(plan.picture)}» - это не та картина; "
                f"свежие номера: cast releases {asked}"
            )
        _shown(env, plans, facts, dress=False, asked=asked).close()
        # Картина проговаривается перед показом: номер молчит, и без этой строки
        # человек узнал бы о подмене уже с экрана.
        env.write(f"играю «{_named(plan.picture)}» - пункт {pick}, названный флагом --pick")
        return plan
    if verdict.refusal:
        raise env.not_found_error(verdict.refusal)
    if not verdict.asks:
        if verdict.note:
            env.write(verdict.note)
        return plan
    if verdict.heading:
        env.write(verdict.heading)  # строка НАД списком: ЧТО нашлось, прежде чем показать
    elif len(plans) == 1 and not env.stdin_is_tty():
        # 🔴 TC-900. --menu вне терминала - просьба «покажи, что есть», а не способ
        # уронить скрипт: картина ровно одна, выбирать не из чего, и «вслепую» тут
        # ничего не выбирается. За терминалом --menu по-прежнему поднимает список
        # из одного пункта и вопрос (TC-578, TC-836) - этой ветки они не касаются.
        env.write(f"подходит картин: 1 - «{_named(plan.picture)}», меню не нужно")
        return plan
    painted = _shown(env, plans, facts, dress=env.stdin_is_tty(), asked=asked)
    try:
        if not env.stdin_is_tty():
            raise env.not_found_error(
                f"подходит картин: {len(plans)}, а терминала нет - вслепую не выбираю; "
                f"назови картину точно (например «{plan.picture.title}») "
                f"или её номер (--pick N), либо запусти cast в терминале"
            )
        if verdict.note:
            env.write(verdict.note)
        default = verdict.number if verdict.takes else None
        return plans[env.ask("Что смотрим?", len(plans), default=default) - 1]
    finally:
        # Меню отвечено: сперва отписываем его от справки, потом отпускаем экран - иначе
        # опоздавшая на миллисекунду строка писала бы уже в чужой вывод.
        if facts is not None:
            facts.watch(None)
        painted.close()
