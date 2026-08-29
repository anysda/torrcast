"""Вопрос «Что смотрим?» и выбор картины меню."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.ports.choice_environment.choice_environment import ChoiceEnvironment
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice._shown import _shown
from torrcast.usecases.choice.absent_first_part import absent_first_part
from torrcast.usecases.choice.absent_part_line import absent_part_line
from torrcast.usecases.choice.certain_default import certain_default
from torrcast.usecases.choice.configure import _environment_port
from torrcast.usecases.choice.default_line import default_line
from torrcast.usecases.choice.first_alive import first_alive
from torrcast.usecases.choice.lone_other_part import lone_other_part
from torrcast.usecases.choice.named_elsewhere import named_elsewhere
from torrcast.usecases.choice.named_take import named_take
from torrcast.usecases.choice.named_taken_line import named_taken_line
from torrcast.usecases.choice.namesake_line import namesake_line
from torrcast.usecases.choice.namesake_take import namesake_take
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
    menu: bool = False,
) -> Plan:
    """Вопрос «какой фильм франшизы?» - и только там, где спрашивать есть о чём.

    🔴 Дефолт у прибора ОДИН - :func:`first_alive`, и это та же картина, о которой
    говорят честные строки про смену (:func:`default_note`, :func:`swap_note`,
    :func:`year_note`, :func:`part_one_swap`). Пока Enter брал верх меню, эти двое
    расходились на 23 запросах из 71, и на всех 23 строка молчала - сверялась она с
    одной картиной, а печаталась про другую.

    🔴 Несколько подошедших картин - ещё не повод спрашивать. Вопрос остаётся там, где
    о выборе есть что сказать честной строкой; где сказать нечего (:func:`certain_default`),
    дефолт - первая живая картина - и есть спрошенная, и показ начинается сам. Молчаливым
    это решение не бывает: :func:`taken_line` называет взятую картину, число подошедших и ход к
    любой другой. Терминал такому пути не нужен вовсе - ни висеть, ни отказываться тут
    не на чем.

    🔴 TC-373. Перескочив через спрошенную часть франшизы (её нет в выдаче или играть
    ей нечем), дефолт вставал на ДРУГУЮ часть - и Enter включал «Тачки 2» вместо
    просимых «Тачек». Такому дефолту не бывать (:func:`part_one_swap`).

    🔴 TC-814. Тот же страж на ветке «картина одна»: меню тут не задавалось вовсе, и
    «лёд» молча включал «Лёд 3». Единственная найденная чужая часть спрошенной
    франшизы - это отказ (:func:`lone_other_part`), а не показ.

    🔴 TC-715. И дефолта нет там, где запрос назвал картину ЦЕЛИКОМ, а дефолт встаёт на
    другую: «блич s1e1» уезжал с «Блича» 2004 года на «Тысячелетнюю кровавую войну»,
    «чернобыль s1e5» - на «Зону отчуждения» мимо обоих «Чернобылей».

    🔴 TC-812. Оба этих стража - и «имя названо целиком» (:func:`named_elsewhere`), и
    тёзки по году - на обычном пути больше НЕ СПРАШИВАЮТ: решение владельца 26-08-2026 -
    «включать самую живую это показатель того что картина популярна а варианты будут уже
    за --menu». Стражи остались стражами: сработавший берёт живейшую не молча
    (:func:`named_taken_line`, :func:`namesake_line`), строка называет взятую годом,
    число остальных и ключ. Вопрос без дефолта у обоих остался только за явным
    ``--menu`` - там человек просил список, и номер называет он сам. Дефолт франшизы это
    не тронуло: первая живая часть и её страж (:func:`part_one_swap`) в силе.

    🔴 TC-830. Разделены два случая, которые страж франшизы стерёг одинаково. «Спрошенная
    часть в выдаче есть, но не играет» - вопрос: её видно номером, и подставлять вместо
    неё другую по-прежнему запрещено. А «спрошенной части нет в выдаче вовсе» вопросом
    быть перестало (:func:`absent_first_part`): выбора между «той» и «другой» там не
    существует, и ``cast тачки`` просил номер из списка, в котором нужного пункта нет, -
    показ без человека не начинался. Берётся дефолт прибора - первая живая из найденных -
    и берётся не молча (:func:`absent_part_line`). За явным ``--menu`` спрашивают оба,
    как и стражи TC-812.

    К каждой картине печатается справка (:mod:`torrcast.runtime.facts_wiring`) — рейтинг,
    хронометраж и фраза о том, что это за кино. 🔴 Ждут из неё ровно ОПИСАНИЕ (TC-717): его
    уже не дописать в показанный список. Рейтинг и хронометраж приезжают в готовые строки
    курсором — зритель видит, как строка дополняется, и отвечает в любую секунду этого
    дописывания.

    Целиком справку ждём там, где дописывать её будет некому (:func:`_shown`).

    🔴 TC-802. ``menu`` - флаг ``--menu``: список поднимается и там, где о выборе сказать
    нечего. Без него подходящую картину прибор берёт сам («тачками» зовутся только
    «Тачки»), и просьба «покажи, что ещё есть» звучит этим флагом, а не отсутствием
    решения. Всё остальное у обоих путей общее: тот же список, тот же дефолт, тот же
    номер в ответе.

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
        if note := lone_other_part(plans, asked):
            # Единственная найденная картина - другая часть спрошенной франшизы. Меню
            # тут не задаётся, выбирать не из чего, а показать её молча - подмена.
            # Ключ --menu пропускается ВПЕРЁД отказа (TC-812): список поднимается и из
            # одного пункта, а строка печатается над ним, чтобы видно было, ЧТО нашлось.
            if not menu:
                raise env.not_found_error(note)
            env.write(note)
        elif not menu or not env.stdin_is_tty():
            # 🔴 TC-900. --menu вне терминала - просьба «покажи, что есть», а не способ
            # уронить скрипт: картина ровно одна, выбирать не из чего, и «вслепую» тут
            # ничего не выбирается. За терминалом --menu по-прежнему поднимает список
            # из одного пункта и вопрос (TC-578, TC-836) - этой ветки они не касаются.
            if menu:
                env.write(f"подходит картин: 1 - «{_named(plans[0].picture)}», меню не нужно")
            return plans[0]
    default = first_alive(plans)
    if not menu:
        if certain_default(plans, asked):
            env.write(taken_line(plans, default, asked))
            return plans[default - 1]
        if absent_first_part(plans, asked):
            # 🔴 TC-830, решение владельца 26-08-2026. Спрошенной части в выдаче нет
            # вовсе: выбирать между «той» и «другой» не из чего, а вопрос сводился к
            # «назови номер», когда нужного номера в списке нет, - и показ без человека
            # не начинался. Берётся дефолт прибора, и берётся вслух.
            env.write(absent_part_line(plans, default, asked))
            return plans[default - 1]
        if not part_one_swap(plans, asked):
            # 🔴 TC-812. Тёзки и целиком названная картина больше не спрашивают: берётся
            # самая живая, и берётся НЕ молча - строка называет взятую, число остальных
            # и ключ --menu, за которым стоят варианты. Вопрос остаётся у стража
            # франшизы (:func:`part_one_swap`) и у явного --menu.
            if taken := named_take(plans, asked):
                env.write(named_taken_line(plans, asked, taken))
                return plans[taken - 1]
            if taken := namesake_take(plans):
                env.write(namesake_line(plans, taken, asked))
                return plans[taken - 1]
    painted = _shown(env, plans, facts, dress=env.stdin_is_tty(), asked=asked)
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
        painted.close()
