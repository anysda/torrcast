"""Что показ говорит вслух и что кладёт в состояние на каждом круге опроса.

Зовёт держатель показа (:func:`torrcast.usecases.revive_playback._hold._hold`).
"""

from __future__ import annotations

import torrcast.usecases.revive_playback._revive_state as _state
from torrcast.domain.position import Position
from torrcast.domain.revive_settings import REVIVE_LIMIT, REVIVE_TRIES
from torrcast.ports.journal import journal
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank import _hms
from torrcast.usecases.revive_playback._revival import _Revival
from torrcast.usecases.revive_playback._screen_state import _Screen
from torrcast.usecases.warm import Warmer
from torrcast.usecases.watch import Watch


def _first_frame(screen: _Screen, feed: Feed, position: Position, session_tag: str) -> None:
    """Был ли на экране КАДР: право CLI сказать «старт NN с» даёт движение указателя."""
    if screen.seen or position.state != "PLAYING":
        return
    # Картинка на экране - теперь CLI имеет право сказать «старт NN с». Право это
    # даёт СДВИНУВШИЙСЯ указатель, а не слово ``PLAYING`` (см. :data:`still_at`):
    # приёмник объявляет себя играющим, ещё не набрав кадров, и на тяжёлом заходе
    # держит указатель на месте старта секунд шесть. Цена честности - один опрос
    # (2 с) запаса в худшую сторону; цена прежней доверчивости была 5-6 с в лучшую.
    if screen.still_at < 0:
        screen.still_at = position.pos
    elif position.pos > screen.still_at:
        screen.seen = True
        _state._revive_playing_mark(feed.out)
        if not screen.raised:
            # Старт приёмник не взял, картинку добыла лестница - и сказать об этом
            # обязаны мы: ``cast`` в этот момент печатает своё «старт NN с» по
            # флажку, а в журнале показа иначе не осталось бы ни строки о том,
            # что чёрный экран кончился.
            screen.raised = True
            print(f"{session_tag} картинка пошла с {_hms(position.pos)}", flush=True)


def _note_transitions(screen: _Screen, feed: Feed, position: Position) -> None:
    """Переходы, о которых след пишет по одному разу: ребуфер и обрыв сети."""
    # Ребуфер - только вход в BUFFERING, а не каждый опрос: иначе счётчик считал бы
    # секунды подвиса, а не сами подвисы. Сеть - на переходе в offline и обратно.
    if position.state == "BUFFERING" and not screen.buffering:
        journal().emit("play", "buffering", pos=round(position.pos, 1))
    screen.buffering = position.state == "BUFFERING"
    if bool(feed.offline) != screen.was_offline:
        screen.was_offline = bool(feed.offline)
        if screen.was_offline:
            # Догадка, а не ответ источника: сюда приходят обрывы, замеченные самой
            # упаковкой (:meth:`torrcast.usecases.feed_pack.feed.Feed._survive`, :meth:`_mute`).
            journal().offline(why=str(feed.offline), asked=False)


def _trace_line(session_tag: str, feed: Feed, position: Position) -> None:
    """Отладочная строка запаса: сколько показано, сколько упаковано и чем расходится."""
    front = feed.front(position.pos)
    print(
        f"{session_tag} запас: показ {position.pos:.0f} · упаковано {front:.0f} · "
        f"впереди {front - position.pos:.0f} с · {feed.weight() / 1e6:.0f} МБ · "
        f"расхождение с манифестом {feed.drift():.3f} с · {position.state}",
        flush=True,
    )


def _report(
    session_tag: str,
    revival: _Revival,
    position: Position,
    feed: Feed,
    warmer: Warmer | None,
) -> None:
    """Строка о состоянии показа раз в :data:`SAY_SECONDS`: экран либо темнота."""
    # ⚠️ Про темноту спрашиваем ровно до тех пор, пока приёмник не показывает.
    # Отметку снимает :meth:`_Revival.alive` ниже по кругу, и между удачным
    # подъёмом и ею умещается один опрос: замер 16-08-2026 на живой приставке -
    # показ поднят в 11:06:20, а строка «картинки нет» ушла в журнал в 11:06:22.
    if (dark := revival.darkness()) and not position.playing:
        # 🔴 Темнота - не «показ с неподвижным указателем». Отчитываться в ней
        # позицией и запасом («экран: 0:01:12 · IDLE», «показ обеспечен до
        # 0:01:12») значит называть чёрный экран показом: кадра на нём нет ни
        # одного, а числа те же, что и у живой картинки. Поэтому строка тут своя,
        # и в ней сказано ровно то, что показ решил сам: сколько уже темно, из-за
        # чего и когда он сдастся, если источник не вернётся.
        # ⚠️ Ноль попыток в темноте - это не сломанный счётчик, а решение: пока
        # источник лежит, LOAD в приёмник не летит вовсе (:func:`_may`).
        # Молча это выглядело как бездействие, и на потолке человек получал
        # «0 попыт.» без единого объяснения, откуда он взялся.
        spent = (
            f"поднимал {revival.tries} из {REVIVE_TRIES}"
            if revival.tries
            else "источник не вернулся - приёмник не трогаю"
        )
        print(
            f"{session_tag} темнота {_hms(dark)} ({revival.why}) - картинки нет; "
            f"{spent}, погашу через {_hms(REVIVE_LIMIT - dark)}",
            flush=True,
        )
    else:
        # Что видит приёмник, тем и отчитываемся: длительность и позиция - это
        # ровно ``duration`` и ``current_time`` из MEDIA_STATUS, снятые владеющим
        # сендером. Другого доказательства «на ТВ есть таймлайн» у нас нет.
        print(
            f"{session_tag} экран: {_hms(position.pos)} из {_hms(position.dur)} · {position.state}",
            flush=True,
        )
        if feed.offline:
            # Обрыв длиннее прогретого не имеет права быть молчаливой смертью:
            # показ говорит, докуда он обеспечен, и продолжает пробовать сеть. В
            # темноте эта строка не печатается: обеспечивать там уже нечего.
            print(
                f"сети нет ({feed.offline}) - показ обеспечен до {_hms(feed.front(position.pos))}",
                flush=True,
            )
    if warmer is not None:
        print(warmer.line(), flush=True)


def _note_watch(watch: Watch, warmer: Warmer | None, held: float, revival: _Revival) -> None:
    """Наружу, через состояние: прогрев, показанный кадр и правда о чёрном экране."""
    # Прогрев виден снаружи только через состояние: живой показ из другого
    # процесса не спросишь (:attr:`torrcast.domain.entry.Entry.warm`).
    if warmer is not None:
        watch.entry.warm = warmer.warmed
    # В закладку уходит показанный кадр, а не указатель приёмника: пока экран
    # стоит, сторож подвиса гонит указатель вперёд, и resume ушёл бы туда,
    # где человек не был (см. ``held``).
    watch.see(held)
    # Тем же каналом наружу уходит и правда о чёрном экране: живой юнит показа не
    # доказывает (:attr:`torrcast.domain.entry.Entry.dark`). Пишется она не по тику
    # сторожа, а сразу на переходе - врать «играю» лишние десять секунд не за что.
    if (watch.entry.dark, watch.entry.dark_why) != (revival.began, revival.why):
        watch.entry.dark, watch.entry.dark_why = revival.began, revival.why
        watch.flush()
