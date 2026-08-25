"""Вопрос «Что смотрим?» и выбор картины меню."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.choice_environment.choice_environment import ChoiceEnvironment
from torrcast.usecases.choice._dress import _dress
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.certain_default import certain_default
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.menu_blocks import menu_blocks
from torrcast.usecases.choice.named_elsewhere import named_elsewhere
from torrcast.usecases.choice.part_one_swap import part_one_swap
from torrcast.usecases.choice.taken_line import taken_line

if TYPE_CHECKING:
    from torrcast.ports.menu_paint import MenuPaint
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
    дефолт - первая живая картина - и есть спрошенная, и показ начинается сам. Молчаливым
    это решение не бывает: :func:`taken_line` называет взятую картину, число подошедших и ход к
    любой другой. Терминал такому пути не нужен вовсе - ни висеть, ни отказываться тут
    не на чем.

    🔴 TC-373. Ограждение того же дефолта: перескочив через спрошенную часть франшизы
    (её нет в выдаче или играть ей нечем), он вставал на ДРУГУЮ часть - и Enter включал
    «Тачки 2» вместо просимых «Тачек». Такому дефолту не бывать (:func:`part_one_swap`):
    строка говорит, что случилось с первой частью, список остаётся на экране, и номер
    называет сам человек.

    🔴 TC-715. И дефолта нет там, где запрос назвал картину ЦЕЛИКОМ, а дефолт встаёт на
    другую: «блич s1e1» уезжал с «Блича» 2004 года на «Тысячелетнюю кровавую войну»,
    «чернобыль s1e5» - на «Зону отчуждения» мимо обоих «Чернобылей». Решение владельца -
    тут не решать вовсе (:func:`named_elsewhere`): строка называет обе картины и причину,
    а номер называет человек.

    К каждой картине печатается справка (:mod:`torrcast.runtime.facts_wiring`) — рейтинг,
    хронометраж и фраза о том, что это за кино. 🔴 Её тут не ждут ВОВСЕ: список печатается
    немедленно, а приехавшее дописывается в уже показанные строки (:func:`_dress`) — зритель видит,
    как строка дополняется, и отвечает в любую секунду этого дописывания.

    Ждём справку ровно там, где дописывать её будет некому (:func:`_shown`).

    ``pick`` - номер пункта, названный флагом ``--pick N``: вопрос тогда не задаётся
    вовсе, и терминал не нужен. Номер берётся из показанного списка - таблицы
    ``cast releases`` или этого меню, - а состав выдачи гуляет от захода к заходу, поэтому
    номер сверяется с запомненным порядком
    (:meth:`ChoiceEnvironment.recalled_pick`): под ним обязана стоять ТА картина, что
    стояла при выдаче номера. Расхождение - отказ, называющий обе картины, а не показ
    соседки. Картина при этом проговаривается вслух в любом исходе - номер молчит.
    Номер вне списка - честная ошибка, а не тихий первый пункт.

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
        plan = plans[pick - 1]
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
    if len(plans) == 1:
        return plans[0]
    default = first_alive(plans)
    if certain_default(plans, asked):
        env.write(taken_line(plans, default, asked))
        return plans[default - 1]
    menu = _shown(env, plans, facts, dress=env.stdin_is_tty(), asked=asked)
    try:
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
        if note := named_elsewhere(plans, asked):
            # Дефолт ушёл бы с картины, чьё имя названо целиком (TC-715) - тогда его
            # нет вовсе: строка называет обе картины и причину, номер зовёт человек.
            env.write(note)
            return plans[env.ask("Что смотрим?", len(plans), default=None) - 1]
        env.write(default_line(plans, default))
        return plans[env.ask("Что смотрим?", len(plans), default=default) - 1]
    finally:
        # Меню отвечено: сперва отписываем его от справки, потом отпускаем экран - иначе
        # опоздавшая на миллисекунду строка писала бы уже в чужой вывод.
        if facts is not None:
            facts.watch(None)
        menu.close()


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
