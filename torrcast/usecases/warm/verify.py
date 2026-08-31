"""Сверка уложенного с сеткой: кусок обязан начаться там, где обещал манифест.

Зовёт её заход прогрева (:func:`_run`) на каждом выложенном куске.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Final

import torrcast.usecases.warm._state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.warm.segment_start import _Clock, segment_start
from torrcast.usecases.warm.settings import SKEW_MAX, SKEW_TRIES
from torrcast.usecases.warm.stall import _stall

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State

#: Кусок лёг на своё место сетки.
FIT: Final = phrase("warm.fit")
#: Кусок лёг раньше своей границы: он уже стёрт и в показ не пойдёт.
SKEW: Final = phrase("warm.skew")
#: Сверить было НЕЧЕМ. Не приговор куску, а признание сторожа: кусок остался лежать.
BLIND: Final = phrase("warm.blind")


def _inspect(
    state: _State,
    done: int,
    edge: int,
    began_of: Callable[[Path], _Clock] = segment_start,
) -> int:
    """Сверить с сеткой всё, что легло после ``done`` и не дальше ``edge``.

    Возвращает новую границу сверенного. Обход не обрывается на первом же промахе, и
    это важнее, чем кажется: ``publish`` выкладывает пачкой (:meth:`_run` опрашивает
    его раз в полсекунды), а заход, вставший не туда, разъезжается с сеткой ЦЕЛИКОМ.
    Оборви обход - и остальные куски пачки остались бы лежать в показе непроверенными,
    то есть сторож ловил бы ровно один кусок из четырёх.

    ``began_of`` - чем узнаётся начало уложенного куска; уезжает в саму сверку.
    """
    for slot in range(max(done + 1, 0), edge + 1):
        _verify(state, slot, began_of)
    return max(done, edge)


def _verify(state: _State, slot: int, began_of: Callable[[Path], _Clock] = segment_start) -> str:
    """Приговор одному уложенному куску: :data:`FIT`, :data:`SKEW` или :data:`BLIND`.

    🔴 Ради этой сверки карточка и написана. Дефект, из-за которого прогрев резал куски
    мимо сетки, прожил незамеченным не потому, что был хитрым, а потому, что уложенное
    никто не сверял: код верил намерению (``-segment_times`` от нужного места), а
    муксер отмерял резы от ПЕРВОГО ПАКЕТА прогона (:meth:`_run`). Куски при этом лежали
    под правильными именами и весили правдоподобно, а начинались на 1.4-3.8 с раньше
    своих границ - на стыке с живой упаковкой метки шли НАЗАД до 1.7 с, около сорока
    кадров дублировалось. Здоровым он выглядел выборочно: там, где в сдвинутом окне не
    оказывалось опорного кадра, рез случайно вставал верно и кусок побайтово совпадал с
    живым. Поэтому сверяется КАЖДЫЙ уложенный кусок, а не один на заход.

    Ловится только сдвиг НАЗАД, и это не полумера. Раньше своей границы кусок начаться
    не может ни по одной законной причине: обе упаковки заходят от измеренного начала
    (:func:`torrcast.adapters.stream_pack.pack_start.pack_start`), а муксер режет по первому
    опорному кадру не раньше границы. Позже - может, и законно: на сетке, чьи границы не попали на
    опорные кадры, муксер ждёт следующего кадра, и ровно так же ведёт себя живая упаковка - её кусок
    в этом месте побайтово тот же самый. Выбрасывать такое значило бы выбрасывать то, что показ и
    так отдаёт с диска; расхождение сетки с потоком - это про карту опорных кадров, и меряет его
    :meth:`torrcast.adapters.stream_pack.packer.Packer.drift`.

    🔴 Не сумев прочесть, сторож отвечает :data:`BLIND`, а НЕ годностью (TC-879). Раньше
    он отвечал годностью, и на приставке (androidtv, CMAF) это была ложная зелень
    сплошняком: у голого ``.m4s`` метки куска - счётчик прогона муксера, а не время фильма
    (:func:`torrcast.usecases.warm.segment_start.segment_start`), сверять их с сеткой нечем, и
    сторож молча отвечал «да» на КАЖДОМ куске - то есть держался зелёным ровно там, где
    мерить не может. Молчание тут хуже любого приговора: пока сторож зелен, никто не
    узнает, что сетка прогрева на этом приёмнике не проверяется вообще.

    Кусок при этом остаётся лежать, и это не поблажка, а замер: бракуя по незнанию, сторож
    выбросил бы на CMAF ВСЁ прогретое до последнего куска, а прогрев переложил бы то же
    самое тем же способом с тем же исходом. Сторож, который бракует по незнанию, дороже
    того дефекта, ради которого он поставлен.

    Говорит он об этом один раз на прогрев, а не на каждом куске: слепота у него не
    случайная, а свойство контейнера, и тысяча одинаковых записей в журнале - это не
    громче одной. Сколько кусков осталось несверенными, считает :attr:`_State.unchecked`.

    Забракованный кусок именно СТИРАЕТСЯ, а не помечается: показ ищет прогретое глобом
    каталога (:meth:`Vault.slots`, :meth:`torrcast.usecases.feed_pack.feed.Feed.segment`), и никакой
    пометки он не читает. Отдачу это не роняет даже в самый неудачный момент - файл,
    пропавший между проверкой и чтением, отдача уже переживает (``OSError`` →
    404 → приёмник просит снова, :meth:`torrcast.adapters.http_server._handler._Handler._read`).

    ``began_of`` - чем узнаётся начало уложенного куска. Доводом, а не именем внутри
    модуля: настоящий замер поднимает ffprobe на настоящем куске, а меряется тут само
    правило сверки - что считается промахом, что дырой и что при этом стирается.
    """
    clock = began_of(state.vault.path(slot))
    began = clock.began
    # Метка куска - это время фильма ПЛЮС начало ленты, одно на все заходы
    # (:attr:`torrcast.adapters.stream_pack.grid.Grid.origin`): сверять надо с тем же числом, иначе
    # порог сдвига у релизов с B-кадрами съеден на треть ещё до всякого промаха.
    want = state.grid.start(slot) + state.grid.origin
    if not clock.movie or math.isnan(began):
        return _blind(state, slot, clock)
    if began > want - SKEW_MAX:
        return FIT
    tries = state.skews.get(slot, 0) + 1
    state.skews[slot] = tries
    state.misgrid = slot if state.misgrid < 0 else state.misgrid
    # Дыра - это честное «тут не прогрето»: файла нет, значит нет его и в
    # :meth:`Vault.slots`, значит "прогрето целиком" (:attr:`done`) не наступит и
    # следующая серия в работу не возьмётся (:meth:`_chain`). Ровно так же считается
    # неготовым тяжёлый кусок, под которым лежит копия (:meth:`_spots_left`).
    hole = tries >= SKEW_TRIES
    state.vault.reject(slot)
    _state._environment.emit("skew", slot=slot, want=want, got=began, hole=hole)
    _state._environment.mark(
        "кусок прогрева мимо сетки", слот=slot, сдвиг=round(began - want, 3), дыра=hole
    )
    where = phrase(
        "warm.skew_where", slot=slot, minute=f"{want / 60:.0f}", diff=f"{began - want:+.2f}"
    )
    if hole:
        _stall(state, phrase("warm.skew_hole", where=where))
    else:
        state._say(phrase("warm.skew_retry", where=where))
    return SKEW


def _blind(state: _State, slot: int, clock: _Clock) -> str:
    """Сверить было нечем: сказать об этом вслух и оставить кусок лежать."""
    why = phrase("warm.blind_why_timecode") if clock.movie else phrase("warm.blind_why_not_movie")
    state.unchecked += 1
    if state.unchecked == 1:
        _state._environment.mark("укладку прогрева не с чем сверить", слот=slot, почему=why)
        state._say(phrase("warm.blind_note", why=why))
    return BLIND
