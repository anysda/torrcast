"""Держим показ: опрос приёмника, живая упаковка, сторож позиции и подъём из темноты.

Зовёт его сценарий показа (:func:`torrcast.usecases.playback._play`), и только он.
"""

from __future__ import annotations

import os
from collections.abc import Callable

import torrcast.usecases.revive_playback._revive_state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.debug_handles import TRACE_ENV
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.start_settings import SAY_SECONDS
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.choice._ctl import _ctl
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.revive_playback._closed import _closed
from torrcast.usecases.revive_playback._endure import _endure
from torrcast.usecases.revive_playback._landing import _landing
from torrcast.usecases.revive_playback._paused import _pause
from torrcast.usecases.revive_playback._poll_step import _poll_step
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
from torrcast.usecases.revive_playback._source_wait import _SourceWait
from torrcast.usecases.revive_playback._tail_cut import _tail_cut
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
    """Держим показ: опрос приёмника раз в 2 с (в окне первого кадра и у конца серии
    перед следующей чаще, :func:`_poll_step`), упаковка должна быть жива, из RAM уходит только
    пройденное, сторож раз в 10 с пишет позицию.

    ``clock`` - чем меряются все выдержки показа (:class:`torrcast.ports.clock.Clock`). Боевой путь
    молчит и берёт часы, которые положил композиционный корень; сухому прогону нужны свои, иначе
    тест выжидал бы терпение приёмника и выдержки между попытками подъёма по-настоящему.

    ``start`` - место, с которого показ заводили. Пока приёмник не назвал ни одной живой
    позиции, поднимать его надо именно отсюда: у мёртвой сессии позиции нет вовсе, и ноль
    вместо закладки вернул бы зрителя к началу фильма, который он смотрит с середины.
    В саму закладку это место не идёт (:attr:`_Screen.held`): закладка - про увиденное.

    ``raised`` - взял ли приёмник старт. ``False`` - показа не было ни кадра, и первым же
    опросом им займётся лестница воскрешения (:meth:`_Revival.resurrect`): смерть на 0:00
    поднимается тем же путём, что и смерть посреди показа.

    ``say_started`` - что сказать, когда приёмник показал ПЕРВЫЙ кадр. Говорится оно по
    сдвинувшемуся указателю (:func:`_first_frame`), а не по взятому LOAD: словом ``PLAYING``
    приёмник отвечает раньше кадра, и «старт NN с» от него - заниженное число.
    """
    clock = clock if clock is not None else _state._revive_clock
    session_tag = session_tag or phrase("playback.session_tag", id=journal().session_id())
    show_trace = bool(os.environ.get(TRACE_ENV))
    #: Всё, что показ помнит между двумя опросами приёмника (:class:`_Screen`).
    screen = _Screen(raised=raised)
    source_wait = _SourceWait(buffer=profile.start_buffer)
    joins = watch is not None and not watch.entry.advance().done  # стык серий впереди
    # Обе выдержки воскрешения - мера молчания ПРИЁМНИКА, поэтому приходят из его профиля,
    # а не из общей константы: приставка после отказа берёт LOAD не так, как телевизор.
    revival = _Revival(
        supply=supply,
        pause=profile.revive_pause,
        lived=profile.revive_pause,
        drop=profile.revive_drop,
        clock=clock,
        buffer=profile.start_buffer,
    )
    while True:
        _ctl(receiver)
        # Выкладка кусков стоит на пути запроса сегмента, а запросов может не быть вовсе:
        # показ на прогретом с диска к упаковке не обращается, и написанное ею копится в
        # памяти (:meth:`torrcast.usecases.feed_pack.feed.Feed.sweep`) - зовут её и по часам.
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
        feed_at = screen.last = position.pos if position.known else screen.held or start
        feed.measured = position.known
        if position.pos > 0 and position.state not in {"BUFFERING", "IDLE"}:
            screen.held = position.pos
        _first_frame(screen, feed, position, session_tag, say_started)
        _note_transitions(screen, feed, position)
        _note_lag(screen, feed, position, clock.monotonic())
        if show_trace:
            _trace_line(session_tag, feed, position)
        if warmer is not None:
            # Прогрев видит тот же запас, что сторож приёмника, и на просевшем
            # замирает (:meth:`torrcast.usecases.warm.warmer.Warmer._throttle`).
            front = feed.front(feed_at)
            warmer.shown(position.pos, position.state == "PLAYING")
            if front < feed.duration:
                warmer.feed(front - feed_at)
            else:
                warmer.packed()  # живая упаковка у конца файла - очередь следующей серии
            if warmer.done and feed.rest():
                print(phrase("revive.fully_warm_switch_disk"), flush=True)
        if clock.monotonic() - screen.said >= SAY_SECONDS:
            screen.said = clock.monotonic()
            _report(session_tag, revival, position, feed, warmer)
        alive = position.state == "PAUSED"  # слово о паузе, по которому показ решает ниже
        paused = alive or (bool(screen.paused) and not position.playing)
        source_wait.check(feed, feed_at, paused or not position.playing, clock.monotonic())
        place = _landing(screen, position)
        if watch is not None:
            _note_watch(watch, warmer, place, revival, paused, screen.buffering)
        if position.state == "ENDED":
            _closed(position, session_tag, screen.held or start, watch)
            return True
        # 🔴 Страховка перехода. Залипший на последнем куске приёмник рапортует BUFFERING, а
        # сторож подвиса молчит: впереди пусто, и неподвижность читается как ожидание упаковки
        # (:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver._nudge`).
        # Показ висел до утра, и терялся переход. Поэтому неподвижный указатель ЗА долей сам
        # кончает сеанс; не отданный упаковкой хвост - обрыв, а не титры (:func:`_tail_cut`).
        if watch is not None and position.playing and watch.entry.ending:
            if position.pos != screen.tail_at:
                screen.tail_at, screen.tail_since = position.pos, clock.monotonic()
            elif clock.monotonic() - screen.tail_since > TAIL_LIMIT:
                if not _tail_cut(watch, feed, position.pos):
                    pos, secs = _hms(position.pos), f"{TAIL_LIMIT:.0f}"
                    print(phrase("revive.tail_ended", pos=pos, secs=secs), flush=True)
                return True
        else:
            screen.tail_at, screen.tail_since = -1.0, 0.0
        # Выше паузы нарочно: закрытый с пульта показ и на закладку возвращать некому.
        if _closed(position, session_tag, screen.held or start, watch):
            return True  # показ убрал с экрана зритель - это конец, а не авария
        # Пауза - решение зрителя, и потеря сессии его не отменяет
        # (:mod:`torrcast.usecases.revive_playback._paused`).
        if paused:
            if not _pause(screen, receiver, feed, profile, clock, alive, screen.held or start):
                return False  # пауза длиной с вечер - показ окончен, юнит гасим
        elif not position.playing:
            # Показ погас. Это конец только тогда, когда поднять его не удалось: обрыв
            # интернета длиннее приёмникова терпения гасит экран, а фильм и место, где
            # его смотрели, никуда не делись (:class:`_Revival`).
            # Поднимают с последнего показанного кадра, а кадра не было - с места, куда
            # показ заводили: ноль закладки значит «зритель не видел ничего», а не «фильм
            # смотрят с начала». Продолжение с середины обязано вернуться в свою середину.
            # Свидетель тут - закладка, а не строгий флаг первого кадра ``seen``: вопрос
            # только в том, назвал ли приёмник живое место (0.0 против 0:02).
            # ⚠️ На конце картины по эху мёртвого сокета о воле зрителя не судят (TC-880).
            shown, sure = screen.held > 0, not position.stale
            still_holding = revival.resurrect(
                receiver, feed, warmer, screen.held or start, shown, sure
            )
            if watch is not None:
                watch.skip_to(revival.resume_at)
            if not still_holding:
                _tail_cut(watch, feed, screen.held or start)  # сдались у конца без хвоста
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
                feed.recoder.played = feed_at
            feed.prune(feed_at)
        clock.sleep(_poll_step(screen, position, joins))
