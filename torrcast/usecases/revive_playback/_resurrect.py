"""Одна ступень подъёма погасшего показа: ждать сеть, стрелять LOAD или гаснуть.

Зовёт её лестница (:meth:`torrcast.usecases.revive_playback._revival._Revival.resurrect`).
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from torrcast.domain.entry import ENDING_RATIO
from torrcast.domain.revive_settings import REVIVE_LIMIT, REVIVE_TRIES
from torrcast.ports.journal import journal
from torrcast.ports.receiver import Receiver
from torrcast.usecases.choice._ctl import _Revivable
from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.revive_playback._blame import _may, _why
from torrcast.usecases.warm.warmer import Warmer

if TYPE_CHECKING:
    from torrcast.usecases.revive_playback._revival_state import _RevivalState


def _resurrect(
    state: _RevivalState,
    receiver: Receiver,
    feed: Feed,
    warmer: Warmer | None,
    pos: float,
    shown: bool = True,
) -> bool:
    """``True`` - показ ещё держим (ждём сеть или только что подняли), ``False`` - гаснем.

    ``pos`` - место, откуда поднимать: последняя позиция, которую приёмник успел
    назвать живой, а не видел ни одной - место, с которого показ заводили. Из мёртвой
    сессии позицию не взять, там ноль, и помнит её показ (:func:`_hold`).

    ``shown`` - был ли на экране хоть один кадр. Врать зрителю «показ погас» там, где
    он не начинался, незачем: строка и запись в ленте про это разные.

    🔴 Ноль отказом больше не является, и это вся суть карточки. Прежде лестница
    отказывалась поднимать показ, у которого указатель не сдвинулся (``pos <= 0``), -
    с формулировкой «поднимать неоткуда». Живые прогоны 15-08-2026 на приставке:
    пять стартов, две смерти на 0:00 - и разница между «фильм досмотрен целиком» и
    «зритель не увидел ничего» была ровно в этом нуле. Указатель успел уехать на
    0:02 - лестница поднимала показ и дальше он шёл как ни в чём не бывало; остался
    на нуле - рабочий юнит выходил, а перед человеком оставался чёрный экран.
    Место у такого показа есть, и оно законное: начало картины. Отрицательного места
    у фильма не бывает - вот его и держим отказом (:data:`torrcast.domain.not_raised.NOT_RAISED`).
    """
    now = state.clock.monotonic()
    if not isinstance(receiver, _Revivable) or pos < 0:
        return False  # поднимать нечем или неоткуда - это обычный конец показа
    if feed.duration > 0 and pos >= feed.duration * ENDING_RATIO:
        return False  # фильм досмотрен: гаснущий экран тут и есть титры, а не авария
    if not state.since:
        state.since, state.warmed = now, warmer.warmed if warmer is not None else 0.0
        why = _why(state, feed)
        state.began, state.why = time.time(), why
        journal().dark(pos=pos, why=why, shown=shown)
        said = (
            f"показ погас на {_hms(pos)}"
            if shown
            else f"показа не было ни кадра (заводили с {_hms(pos)})"
        )
        print(f"{said} ({why}) - подниму сам, как вернётся сеть", flush=True)
    dark = now - state.since
    if state.tries >= REVIVE_TRIES or dark > REVIVE_LIMIT:
        print(
            f"показ поднять не удалось ({state.tries} попыт., темнота {dark:.0f} с) - "
            f"гашу; cast продолжит с {_hms(pos)}",
            flush=True,
        )
        state.ended = True
        return False
    if not _may(state, feed, warmer, pos) or (state.last and now - state.last < state.pause):
        return True  # сети всё ещё нет либо выдержка между попытками не вышла
    if state.dropped and dark < state.drop:
        # 🔴 Показ бросил сам приёмник, источник цел - и признаки «сеть вернулась»
        # про приёмник не говорят ровно ничего. Прогрев в этот момент растёт всегда
        # (служба раздач жива, куски идут), :attr:`Feed.offline` пуст всегда - поэтому
        # первая попытка выстреливала в темноту нулевой длины и сгорала впустую.
        # Ждать тут можно одно - самого приёмника, а мера его молчания - время.
        #
        # ⚠️ Времени этого - секунды, а не минута: приёмник, бросивший показ, берёт
        # LOAD через 3-4 с (:data:`REVIVE_DROP`), и минута ожидания была минутой
        # чёрного экрана впустую. Осторожность живёт дальше по коду - в выдержке между
        # попытками со второй (:attr:`pause`), где она и заработана замером.
        return True
    state.tries, state.last = state.tries + 1, now
    came = "приёмник отмолчался" if state.dropped else "сеть вернулась"
    print(f"{came} - поднимаю показ с {_hms(pos)} (попытка {state.tries})", flush=True)
    # 🔴 Отвечает приёмник МЕСТОМ, а не согласием, и место это бывает не тем, о котором
    # просили: кусок, на котором показ уже умирал, ему больше не отдаётся
    # (:meth:`torrcast.adapters.chromecast.cast.ChromecastReceiver._past_deadly`), и подъём уезжает
    # за него - до пятнадцати секунд фильма. Пока эта строка называла ``pos``, она называла место,
    # где показ как раз НЕ пошёл, - ровно поверх честной строки о перешагнутом куске. Двух мнений о
    # том, откуда идёт фильм, у зрителя быть не должно. ⚠️ Удачу отличает знак, а не «непусто»:
    # поднятый с начала картины показ отвечает нулём, и он же - законное место
    # (:data:`torrcast.domain.not_raised.NOT_RAISED`).
    back = receiver.replay(pos)
    raised = back >= 0
    journal().revive(pos=back if raised else pos, tries=state.tries, waited=dark, ok=raised)
    print(
        f"показ поднят с {_hms(back)}"
        if raised
        else "приёмник показ не взял - жду ещё (или он занят чужим показом)",
        flush=True,
    )
    return True
