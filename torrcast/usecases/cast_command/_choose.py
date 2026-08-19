"""Меню франшизы, прогрев под него и отбор релиза - весь путь до готового к показу файла.

Зовёт его команда показа (:func:`_cmd_play`), и только она.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

import torrcast.usecases.cast_command._play_state as _state
from torrcast.domain.config import Config
from torrcast.domain.prewarm_settings import PREWARM
from torrcast.ports.journal import journal
from torrcast.ports.progress import progress as progress_bar
from torrcast.usecases.cast_command._bookmark import _continue_picked
from torrcast.usecases.choice._passport import _passport
from torrcast.usecases.choice._pick_plan import _pick_plan
from torrcast.usecases.choice._played import _played
from torrcast.usecases.choice.warm_order import warm_order
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.reinforce._timed import _timed
from torrcast.usecases.reinforce._topup import _topup
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.start_clock import _Clock

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.domain.choice import Choice
    from torrcast.domain.entry import Entry
    from torrcast.domain.watch_state import WatchState
    from torrcast.usecases.choice._passport import _Passport
    from torrcast.usecases.select.plan import Plan

    #: Чем кончается путь до релиза: набор для показа или КОД от закладки картины.
    Chosen = tuple[list[Plan], Plan, _Prep, Bench, _Passport] | int


def _choose(
    config: Config,
    args: Args,
    chosen: Choice,
    state: WatchState,
    live: tuple[str, Entry] | None,
    clock: _Clock,
    *,
    circle: Callable[..., list[Plan]] = search_circle,
    stand: Callable[..., Bench] = Bench,
    passport_of: Callable[..., _Passport] = _passport,
    pick: Callable[..., Plan] = _pick_plan,
    bookmark: Callable[..., int | None] = _continue_picked,
) -> Chosen:
    """Найти, спросить и отобрать: планы меню, выбранная картина и готовый релиз.

    Вместо набора отсюда бывает КОД: закладка выбранной картины отвечает показом прямо
    здесь (:func:`_continue_picked`), а звать её раньше меню нельзя - она про место ВНУТРИ
    картины, и картина к этой секунде ещё не названа.

    Круг поиска, стенд отбора, фоновая справка, вопрос о картине и закладка названы
    аргументами с боевым умолчанием: работа этой единицы - порядок, в котором их зовут,
    и зеркалу надо мерить именно порядок, а не сеть и не рой за каждым из них.
    """
    with progress_bar() as progress:
        plans = circle(config, args, progress, chosen.profile)
        # Справка к меню (рейтинг, хронометраж, о чём кино) едет фоном - ровно в те
        # секунды, что уходят на подъём прогрева. Меню её не ждёт: см. torrcast.runtime.facts_wiring.
        facts = _state._play_facts([(p.picture.title, p.picture.year) for p in plans])
        facts.start()
        # 🔴 TC-199/TC-200. Год картины, которая встанет дефолтом, сверяется со справкой -
        # так же, как добор сверяет свой (:func:`year_note`). Справку зовём вслепую и фоном,
        # ровно в те секунды, что уходят на меню и прогрев: путь до меню её не ждёт, а к
        # последней строке перед стартом паспорт уже приехал. Год выдачи ей НЕ сообщаем -
        # иначе подстроится под подмену и сверять станет нечего.
        passport = passport_of(plans)
        torrserver = _state._play_engines(config.torrserver_url)
        bench = stand(torrserver, choose=file_picker(args), profile=chosen.profile)
        # Прогрев под меню: пока идёт вопрос, раздачи уже качают метаданные. Греется
        # голова ОЧЕРЕДИ, а не верх ранжира: верх мог не пройти ворота (TC-432), и
        # греть то, что отбор не возьмёт, - тянуть чужой вес из роя зря.
        order = warm_order(plans)
        # 🔴 Пока на экране идёт наш показ, прогрев под меню не поднимается вовсе: он
        # тянет из роя чужие раздачи, пишет их на тот же диск и читает ту же сеть, а
        # показ первичен. Человек ещё не выбрал картину, и платить за его раздумья
        # обязаны мы скоростью своего меню, а не зритель - картинкой.
        prewarm = [] if live is not None else order[:PREWARM]
        for plan in prewarm:
            # Номер, названный руками, у каждой картины меню свой, и у части их столько
            # раздач не наберётся: спрос с той, которую человек выберет, - за отбором.
            if args.release is not None and not 1 <= args.release <= len(plan.ranked):
                continue
            if queue := plan.candidates(args):
                bench.start(plan, queue[0])
        # ...и запасной релиз той картины, в которую попадёт Enter: брак верха не должен
        # стоить человеку подъёма второй раздачи с нуля (:data:`PREWARM_SPARE`).
        if live is None:
            bench.spare(order[0], args)
        journal().mark("прогрев пущен", придержан=live is not None)  # TC-108: замер
        try:
            try:
                plan = pick(plans, facts, pick=args.pick, asked=args.title_query)
                journal().mark("картина выбрана")  # TC-108: замер
                # Картина названа - вот теперь очередь закладки: она про место ВНУТРИ
                # картины, и спрашивают о ней после того, как картина выбрана.
                code = bookmark(config, state, plan, bench, args=args, clock=clock)
                if code is not None:
                    return code
                if args.release is not None:
                    args.release_hash = _state._play_pinned(
                        args.title_query, plan.picture.key, args.release
                    )
                # Опоздавший индексер: круг ушёл по кворуму, и его выдача доехала, пока
                # человек читал меню. Доливаем ЗДЕСЬ - список уже прочитан и отвечен,
                # менять под курсором нечего (:func:`_topup`). Ключи меню ему нужны,
                # чтобы отличить картину, которой в списке не было (о ней - честная
                # строка), от соседней по меню (о ней говорить «её не было» - соврать).
                plan = bench.reorder(
                    plan,
                    _topup(
                        plan,
                        args,
                        config,
                        chosen.profile,
                        progress,
                        menu=frozenset(p.picture.key for p in plans),
                    ),
                )
                # Справка уже дождана меню - её хронометраж встаёт в знаменатель
                # битрейта вместо прикидки (:func:`_timed`), и порядок отбора
                # пересобирается на настоящих числах. Прогретое при этом не пропадает:
                # номера релизов переезжают вместе с порядком (:meth:`Bench.reorder`).
                plan = bench.reorder(plan, _timed(plan, facts, args, config, chosen.profile))
                _state._play_native(plan.picture, args.title_query)
                # Прогретые кандидаты ДРУГИХ картин с этой секунды - мусор: они тянут
                # куски у той раздачи, которую сейчас будем показывать, и всё это время
                # стоят в TorrServer лишними (:meth:`Bench.keep_plan`).
                bench.keep_plan(plan)
            finally:
                # Меню уже на экране, и ответ на него получен: пусть фоновый добор допишет
                # кэш - СЛЕДУЮЩЕЕ меню этой франшизы будет полным. Ко времени до меню это
                # отношения не имеет, а к моменту ответа поток обычно давно закончил.
                facts.finish()
            plan, prep = _played(bench, plans, plan, args, progress, facts, config, chosen.profile)
            journal().mark("отбор релиза", релиз=prep.number)  # TC-108: замер
        except BaseException:  # Ctrl-C, «картин много, а терминала нет», «годного нет»
            bench.drop_all()  # прогретое без показа - мусор в рое и кэш в чужой RAM
            raise
        bench.keep_only(prep)  # прогрев греет лишнее - до показа лишнее убираем
    return plans, plan, prep, bench, passport
