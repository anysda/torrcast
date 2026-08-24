"""Держим показ: опрос приёмника, живая упаковка, сторож позиции и подъём из темноты.

Зовёт его сценарий показа (:func:`torrcast.usecases.playback._play`), и только он.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import torrcast.usecases.revive_playback._revive_state as _state
from torrcast.domain.debug_handles import TRACE_ENV
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.start_settings import FIRST_FRAME_POLL, SAY_SECONDS
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.choice._ctl import _ctl
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.revive_playback._endure import _endure
from torrcast.usecases.revive_playback._paused import _pause
from torrcast.usecases.revive_playback._revival import _Revival
from torrcast.usecases.revive_playback._revive_state import TAIL_LIMIT
from torrcast.usecases.revive_playback._screen import (
    _first_frame,
    _note_lag,
    _note_transitions,
    _note_watch,
    _report,
    _trace_line,
)
from torrcast.usecases.revive_playback._screen_state import _Screen
from torrcast.usecases.warm.warmer import Warmer
from torrcast.usecases.watch import Watch


def _hold(
    receiver: Receiver,
    feed: Feed,
    watch: Watch | None = None,
    warmer: Warmer | None = None,
    supply: StreamSource | None = None,
    profile: Profile = CAUTIOUS,
    clock: Clock | None = None,
    session_tag: str = "",
    start: float = 0.0,
    raised: bool = True,
    say_started: Callable[[], None] = lambda: None,
) -> bool:
    """Держим показ: опрос приёмника раз в 2 с (между словом ``PLAYING`` и первым
    кадром - раз в :data:`FIRST_FRAME_POLL`), упаковка должна быть жива, из RAM уходит
    только пройденное, сторож раз в 10 с пишет позицию.

    Перемотку здесь ловить больше нечем и незачем: приёмник видит весь фильм и на seek
    просто просит сегмент нужного места, а :class:`Feed` пакует оттуда.
    Показу остаётся то, о чём раздача не знает: пауза на пульте и конец показа.

    Придерживать ffmpeg сигналом (SIGSTOP) здесь больше нечем и незачем: темп держит
    сам ffmpeg (``-readrate`` + ``-readrate_initial_burst``), а под паузой процесс
    именно завершается — под SIGSTOP'ом приёмник намертво вис в BUFFERING.

    ``clock`` - чем меряются все выдержки показа (:class:`torrcast.ports.clock.Clock`).
    Боевой путь молчит и берёт часы, которые положил композиционный корень; сухому
    прогону нужны свои, иначе тест выжидал бы терпение приёмника и выдержки между
    попытками подъёма по-настоящему.

    ``start`` - место, с которого показ заводили. Пока приёмник не назвал ни одной живой
    позиции, поднимать его надо именно отсюда: у мёртвой сессии позиции нет вовсе, и ноль
    вместо закладки вернул бы зрителя к началу фильма, который он смотрит с середины.
    В саму закладку это место не идёт (:attr:`_Screen.held`): закладка - про увиденное.

    ``raised`` - взял ли приёмник старт. ``False`` - показа не было ни кадра, и первым же
    опросом им займётся лестница воскрешения (:meth:`_Revival.resurrect`): смерть на 0:00
    поднимается тем же путём, что и смерть посреди показа.

    ``say_started`` - что сказать, когда приёмник показал ПЕРВЫЙ кадр. Говорится оно
    по сдвинувшемуся указателю (:func:`_first_frame`), а не по взятому LOAD: словом
    ``PLAYING`` приёмник отвечает раньше кадра, и «старт NN с» от него - заниженное
    число.
    """
    clock = clock if clock is not None else _state._revive_clock
    session_tag = session_tag or f"[сеанс {journal().session_id()}]"
    show_trace = bool(os.environ.get(TRACE_ENV))
    #: Всё, что показ помнит между двумя опросами приёмника (:class:`_Screen`).
    screen = _Screen(raised=raised)
    # Обе выдержки воскрешения - мера молчания ПРИЁМНИКА, поэтому приходят из его профиля,
    # а не из общей константы: приставка после отказа берёт LOAD не так, как телевизор.
    revival = _Revival(
        supply=supply,
        pause=profile.revive_pause,
        lived=profile.revive_pause,
        drop=profile.revive_drop,
        clock=clock,
    )
    while True:
        _ctl(receiver)
        # Выкладка кусков стоит на пути запроса сегмента, а запросов может не быть вовсе:
        # показ, который берёт прогретое с диска, к упаковке не обращается, и написанное
        # ею копится в памяти (:meth:`torrcast.usecases.feed_pack.feed.Feed.sweep`). Поэтому её зовут
        # ещё и по часам показа - здесь, до всякого разговора с приёмником.
        feed.sweep()
        if trouble := feed.trouble():
            screen.was_offline = _endure(feed, supply, clock, trouble, screen.was_offline)
            continue
        try:
            # Запас упаковки идёт приёмнику: неподвижный BUFFERING при готовых сегментах
            # впереди - это зависание, а при пустых - законное ожидание нас.
            position = receiver.position(feed.front(screen.last))
        except InfraError:  # приёмник позицию не отдаёт - показу остаётся только ждать
            clock.sleep(2.0)
            continue
        screen.last = position.pos
        if position.pos > 0 and position.state not in {"BUFFERING", "IDLE"}:
            screen.held = position.pos
        _first_frame(screen, feed, position, session_tag, say_started)
        _note_transitions(screen, feed, position)
        _note_lag(screen, feed, position, clock.monotonic())
        if show_trace:
            _trace_line(session_tag, feed, position)
        if warmer is not None:
            # Приоритет живого окна держится ровно здесь: прогрев видит тот же запас, что
            # и сторож приёмника, и на просевшем замирает
            # (:meth:`torrcast.usecases.warm.warmer.Warmer._throttle`).
            warmer.feed(feed.front(position.pos) - position.pos)
            if warmer.done and feed.rest():
                print("прогрето целиком - живую упаковку гашу, показ идёт с диска", flush=True)
        if clock.monotonic() - screen.said >= SAY_SECONDS:
            screen.said = clock.monotonic()
            _report(session_tag, revival, position, feed, warmer)
        if watch is not None:
            _note_watch(watch, warmer, screen.held, revival)
        # 🔴 Страховка перехода. Конец потока приёмник называет не всегда: залипший на
        # последнем куске рапортует BUFFERING и живым себя считать не перестаёт, а сторож
        # подвиса на нём молчит по своему же правилу - впереди честно пусто, потому что
        # картина кончилась, и неподвижность он читает как законное ожидание упаковки
        # (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver._nudge`).
        # Сеанс в этом месте не кончался вовсе: показ висел до утра, следующая серия не начиналась,
        # и терялся именно переход - то, что дороже хвоста. Поэтому неподвижный указатель ЗА долей
        # длительности сам кончает сеанс: дальше конец разбирает :meth:`Watch.close`.
        if watch is not None and position.playing and watch.entry.ending:
            if position.pos != screen.tail_at:
                screen.tail_at, screen.tail_since = position.pos, clock.monotonic()
            elif clock.monotonic() - screen.tail_since > TAIL_LIMIT:
                print(
                    f"конец картины: указатель стоит на {_hms(position.pos)} уже "
                    f"{TAIL_LIMIT:.0f} с - считаю доигранным",
                    flush=True,
                )
                return True
        else:
            screen.tail_at, screen.tail_since = -1.0, 0.0
        # Пауза - решение зрителя, и потеря сессии его не отменяет: слово приёмника
        # здесь может быть потеряно (UNKNOWN с нулём), и ветка держится на памяти
        # показа, а не на нём (:mod:`torrcast.usecases.revive_playback._paused`).
        if (alive := position.state == "PAUSED") or (screen.paused and not position.playing):
            if not _pause(screen, receiver, feed, profile, clock, alive, screen.held or start):
                return False  # пауза длиной с вечер - показ окончен, юнит гасим
        elif not position.playing:
            # Показ погас. Это конец только тогда, когда поднять его не удалось: обрыв
            # интернета длиннее приёмникова терпения гасит экран, а фильм и место, где
            # его смотрели, никуда не делись (:class:`_Revival`).
            # Поднимают с последнего показанного кадра, а кадра не было - с места, куда
            # показ заводили: ноль закладки значит «зритель не видел ничего», а не «фильм
            # смотрят с начала». Продолжение с середины обязано вернуться в свою середину.
            # ⚠️ Свидетель показа тут - закладка, а не флаг ``seen``: тот про право CLI
            # сказать «старт NN с» и потому строже (ему нужен сдвиг указателя). Здесь
            # вопрос другой - назвал ли приёмник хоть одно живое место, - и ответ на него
            # ровно тот же, по которому показ отличает свои две смерти: 0.0 против 0:02.
            if not revival.resurrect(
                receiver, feed, warmer, screen.held or start, shown=screen.held > 0
            ):
                return revival.ended
            # Причину темноты добывает сам :class:`_Revival`, спрашивая источник, и в след
            # она уже легла (:func:`_why`). Второй раз то же событие не пишем.
            screen.was_offline = bool(feed.offline)
        else:
            # Кадр на экране или ожидание его - разница тут в том же, в чём и у закладки:
            # запас попыток возвращает прожитая картинка, а не прожитый BUFFERING.
            revival.alive(position.state == "PLAYING")
            screen.paused = 0.0
            if feed.recoder is not None:
                feed.recoder.played = position.pos
            feed.prune(position.pos)
        # Между словом ``PLAYING`` и доказанным кадром приёмник спрашивается чаще: флажок
        # «картинка» ставится только на этом круге, и при шаге 2 с строка «старт NN с»
        # запаздывала за настоящим кадром на 1.9-3.8 с (:data:`FIRST_FRAME_POLL`). До слова
        # ``PLAYING`` кадру взяться неоткуда, на паузе и в темноте указатель не двигается -
        # там окна старта нет, и шаг обычный.
        clock.sleep(
            2.0
            if screen.seen or screen.still_at < 0 or position.state in {"PAUSED", "IDLE"}
            else FIRST_FRAME_POLL
        )
