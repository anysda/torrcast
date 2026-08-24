"""Закладка выбранной картины: продолжить, начать сначала или списать досмотренное.

Зовёт их команда показа (:func:`_cmd_play`) - каждую на своём раннем выходе. Прогрев
под меню спрашивает у закладки, ответит ли она за картину сама (:func:`_plays_recorded`).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.playback._launch import _launch
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.select._about import _about
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.select._voiced import _Voiced, _voiced
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.start_clock import _Clock

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan


def _continue_picked(
    config: Config, state: WatchState, plan: Plan, bench: Bench, *, args: Args, clock: _Clock
) -> int | None:
    """Закладка выбранной картины поднимается после «Что смотрим?», а не вместо него.

    🔴 Сохранённая позиция отвечает на вопрос «где я остановился», а не «какую картину я
    прошу». По имени франшизы без номера она и не спрашивается вовсе
    (:func:`torrcast.domain.watch_state._other_part`): такой запрос зовёт первую часть,
    а меню называет остальные. Потерять её при этом нельзя - продолжение с места и есть
    то, ради чего
    закладка живёт, - поэтому здесь у неё своя очередь: картина уже названа, ключ её
    известен, и запись берётся по ключу картины, а не по тексту запроса.

    Начатая картина после выбора продолжается молча
    (:func:`torrcast.usecases.playback._launch._resume`), поэтому единственный возможный диалог на
    этом пути - выбор самой картины.

    Условие повторяет ту ветку :func:`_continue`, которая точно отвечает показом: фильм,
    начатый и не досмотренный. Прогретое под меню убирается до продолжения: записанная
    раздача известна, а конкурирующий читатель отнял бы полосу у показа.

    Названный руками релиз (``--release N`` / ``--file N``) сюда не заходит: там человек
    выбирает раздачу сам, а продолжение играет записанную.

    🔴 Но молча мимо закладки такой показ не проходит. Названный релиз играется с начала,
    и стартовая запись показа (:func:`torrcast.usecases.playback._launch`) кладётся под тот же ключ
    картины - сохранённое место после этого не восстановить ниоткуда. ``--release N``
    значит «другая раздача», а не «забудь, где
    я остановился», и разницу эту человек обязан увидеть строкой до старта, а не следующим
    запуском. Строка одна и только когда терять правда есть что (:attr:`Entry.resumable`).

    Дверь меню (``--menu``, ``--pick N``) в том же исходе молчала: начатый сериал, взятый
    из меню, уходит обычным путём с нуля (его ветка здесь не отвечает), и стартовая запись
    сносит сохранённое место под тем же ключом. Строка там своя: причиной названа та дверь,
    которой вошли («картина выбрана в меню»), а хвост о потере общий - потеря-то одна.
    Начатый фильм из меню продолжается, как и без ручек: терять там нечего.
    """
    started = state.get(plan.picture.key)
    if started is None:
        return None
    if args.pinned and args.from_start:
        named = "релиз" if args.release is not None else "файл"
        print(
            f"«{started.title}» - {named} назван руками, играю выбранное с начала; "
            "сохранённый выбор не поднимаю"
        )
    elif args.pinned and started.resumable:
        print(
            f"«{started.title}» - релиз назван руками, играю с начала; "
            f"сохранённое место {_hms(started.pos)} не поднимаю"
        )
    if args.pinned:
        return None
    if args.from_start:
        bench.drop_all()
        return _from_start(config, plan.picture.key, started, args=args, clock=clock)
    if started.serial or not started.resumable:
        if args.from_menu and started.resumable:
            # Голова строки называет ту дверь, которой вошли: картину выбрали в меню, её
            # закладка здесь не отвечает, и показ с нуля перепишет сохранённое место под
            # тем же ключом. Потеря та же, что у названного руками релиза выше, - хвост общий.
            print(
                f"«{started.title}» - картина выбрана в меню, играю с начала; "
                f"сохранённое место {_hms(started.pos)} не поднимаю"
            )
        return None
    bench.drop_all()
    return _continue(config, plan.picture.key, started, args=args, clock=clock)


def _plays_recorded(state: WatchState, key: str, args: Args) -> bool:
    """Ответит ли закладка этой картины показом записанной раздачи - и снесёт прогретое.

    Спрашивает прогрев под меню до подъёма раздачи картины
    (:func:`torrcast.usecases.cast_command._choose._choose`): закладка играет ЗАПИСАННУЮ
    раздачу, поэтому прогретый кандидат такой картины не пригодится при любом ответе -
    выбери человек её, прогретое снесёт сама закладка (:func:`_continue_picked`), выбери
    соседнюю - его уберёт уборка чужих картин
    (:meth:`torrcast.usecases.select_bench.bench.Bench.keep_plan`). Условие обязано совпадать с
    условием самой закладки знак в знак, поэтому живёт рядом с ней.
    """
    started = state.get(key)
    if started is None or args.pinned:
        return False
    return args.from_start or (args.episode is None and not started.serial and started.resumable)


def _from_start(config: Config, key: str, entry: Entry, *, args: Args, clock: _Clock) -> int | None:
    """Сохранённая раздача с нуля; ``None`` - запрос требует обычного поиска.

    Названная серия ищется в таблице той же раздачи. Дорожку, названную ``--voice``,
    перечитываем тем же путём, что продолжение, и передаём поднятую раздачу показу.
    """
    if args.episode is not None:
        jumped = entry.jump(args.episode.season, args.episode.episode)
        if jumped is None:
            return None
        entry = jumped
    else:
        entry = replace(entry, pos=0.0, done=False)
    own = _Voiced()
    try:
        entry = _voiced(config, entry, args, own)
        code = _launch(config, key, entry, _about(entry), clock, args.dry)
        own.handed = not args.dry
        return code
    finally:
        own.drop(config)


def _account_watched(state: WatchState, found: tuple[str, Entry]) -> tuple[tuple[str, Entry], bool]:
    """На следующем ``cast`` превратить закладку >= 95 % в «досмотрено».

    Это бухгалтерия сохранённого места, не переход играющего сериала: живой юнит
    по-прежнему берёт следующую серию только после естественного конца потока.
    """
    key, entry = found
    if entry.done or not entry.watched:
        return found, False
    stopped, label = entry.pos, entry.label
    following = entry.advance()
    state.put(key, following)
    watch_store().save(state)
    if following.serial and following.done:
        return (key, following), True  # строку и выбор перезапуска ведёт ``_continue``
    what = f" {label}" if label else ""
    decision = (
        f"играю {following.label}" if following.serial and not following.done else "играю с начала"
    )
    print(f"«{entry.title}»{what} досмотрено на {_hms(stopped)} из {_hms(entry.dur)} - {decision}")
    return (key, following), True
