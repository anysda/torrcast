"""Закладка выбранной картины: продолжить, начать сначала или списать досмотренное.

Зовёт их команда показа (:func:`_cmd_play`) - каждую на своём раннем выходе.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store import store as watch_store
from torrcast.usecases.playback import _launch
from torrcast.usecases.rank import _hms
from torrcast.usecases.select import _about, _continue, _Voiced, _voiced
from torrcast.usecases.select_bench import _Bench
from torrcast.usecases.start_clock import _Clock

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select._plan import _Plan


def _continue_picked(
    config: Config, state: WatchState, plan: _Plan, bench: _Bench, *, args: Args, clock: _Clock
) -> int | None:
    """Закладка выбранной картины поднимается после «Что смотрим?», а не вместо него.

    🔴 Сохранённая позиция отвечает на вопрос «где я остановился», а не «какую картину я
    прошу». По имени франшизы без номера она и не спрашивается вовсе
    (:func:`torrcast.domain.watch_state._other_part`): такой запрос зовёт первую часть,
    а меню называет остальные. Потерять её при этом нельзя - продолжение с места и есть
    то, ради чего
    закладка живёт, - поэтому здесь у неё своя очередь: картина уже названа, ключ её
    известен, и запись берётся по ключу картины, а не по тексту запроса.

    Начатая картина после выбора продолжается молча (:func:`torrcast.cli._resume`), поэтому
    единственный возможный диалог на этом пути - выбор самой картины.

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
        return None
    bench.drop_all()
    return _continue(config, plan.picture.key, started, args=args, clock=clock)


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
