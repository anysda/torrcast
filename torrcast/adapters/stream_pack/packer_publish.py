"""Выкладка дописанного наружу: переименование, склейка со звуком копии и потолок веса.

Зовёт её :meth:`torrcast.adapters.stream_pack.packer.Packer.publish`, и только он.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack._segment_files import _names
from torrcast.adapters.stream_pack._shrunk_out import _shrunk_out
from torrcast.adapters.stream_pack.done_slots import done_slots
from torrcast.adapters.stream_pack.key_missing import key_missing
from torrcast.adapters.stream_pack.merge_tracks import merge_tracks
from torrcast.adapters.stream_pack.timeline_shift import timeline_shift
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.domain.hls_settings import MIXED_PREFIX
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer_state import _State


def _lay_out(
    state: _State,
    finished: Callable[[], bool],
    *,
    merge: Callable[..., bool] = merge_tracks,
    shift_of: Callable[[Path, Path], float | None] = timeline_shift,
    keyless: Callable[[Path], bool] = key_missing,
) -> None:
    """Выложить наружу куски, которые ffmpeg уже дописал.

    Дописан тот, за которым появился следующий, а хвост сетки - ещё и тот, кто дорезан
    до конца фильма (:func:`done_slots`): соседа муксер открывает и после реза не по
    нашему списку, а такой хвост вдвое короче своего места в манифесте. Последний кусок
    соседа не получит никогда, поэтому за него отвечает отдельный признак
    (:meth:`Packer.finished`).
    Докатка (номер меньше ``first``) не выкладывается никогда — она короче своего
    места в манифесте и под её именем может лежать честный сегмент прошлого прогона.

    Признак «прогон дочитал вход» приходит доводом, а не спрашивается у класса: подменяют
    его наследники прогона на стендах показа, а импортировать сюда сам класс нельзя -
    выкладка живёт внутри него.

    Тем же доводом приезжают ``merge`` (склейка картинки перекода со звуком копии),
    ``shift_of`` (сдвиг ленты, нужный ужатию на месте) и ``keyless`` (не начинается ли
    перекод БЕЗ опорного кадра): все трое поднимают ffmpeg и ffprobe на настоящих кусках,
    а здесь меряется РЕШЕНИЕ выкладки - что уходит наружу и куда встаёт край.
    """
    slots = sorted(s for s in map(segment_slot, _names(state.run)) if s >= 0)
    if not slots:
        return
    # Прогон дочитал вход до конца - дописан и последний кусок (:meth:`finished`).
    # Любой другой исход (жив, убит, оборвался) последний кусок дописанным не делает.
    done = done_slots(state, slots, finished())
    for slot in done:
        path = state.run / segment_name(slot)
        # Ниже своего первого - докатка, выше последнего - обрезок за ``-to``
        # (:attr:`last`). И то и другое короче своего места в манифесте, и наружу
        # такое отдавать нельзя ни при каких обстоятельствах.
        if slot < state.first or 0 <= state.last < slot:
            path.unlink(missing_ok=True)
            continue
        # Кусок сейчас перекодируют - подождём его (:attr:`hold`). Дальше по списку не
        # идём: выложить следующий, оставив дыру, значит увести край за неё, и запрос
        # придержанного места выглядел бы для :meth:`Feed._steer` перемоткой назад.
        #
        # Спрашивающему отдаётся ВЕС уже готовой копии, и это не оптимизация, а
        # единственный честный замер: предсказание по карте зажато потолком
        # перекодирования и на «Тачках 3» промахнулось вчетверо (11.7 МБ против
        # 51.4). Стоит он один ``stat`` на выложенный сегмент.
        size = 0
        with contextlib.suppress(OSError):
            size = path.stat().st_size
        if state.hold is not None and state.hold(slot, size):
            break
        # Перекодированный кусок этого же места лучше копии: то же разрешение и те же
        # метки, но битрейт, который приёмник тянет. Копия при этом выбрасывается.
        better = state.spare / segment_name(slot) if state.spare is not None else None
        # 🔴 TC-698. Перекод без опорного кадра в начале - это кусок БЕЗ КАРТИНКИ, а не
        # кусок похуже: склейка идёт ``-c copy``, а копирование выбрасывает всё до первого
        # опорного кадра, и когда его нет вовсе - выбрасывает всё видео. Живой замер: 12
        # таких кусков из 39, приёмник умирает на них трижды за четыре минуты, КПД 0.47
        # против 0.94. Такой перекод не спасти ни склейкой, ни выкладкой как есть (сегмент
        # обязан быть самостоятельным), поэтому он тут же и сносится: дальше место идёт
        # обычным путём копии, то есть ужатием на месте.
        if better is not None and better.exists() and keyless(better):
            journal().mark("перекод без опорного кадра", слот=slot)
            better.unlink(missing_ok=True)
        source, how = path, "копия"
        if better is not None and better.exists():
            # Наружу идёт картинка перекода со звуком копии (:func:`merge_tracks`):
            # звук показа обязан остаться одним непрерывным потоком.
            #
            # 🔴 Метки картинке НЕ правятся: оба захода пакуют ленту фильма (``-copyts``
            # и общий :attr:`~.grid.Grid.origin`), а голова куска копии лентой не является.
            # Муксер режет поток в порядке ДЕКОДИРОВАНИЯ по условию на время показа, и она
            # встаёт тем раньше границы, чем сильнее переупорядочен кадр на ней, - от куска
            # к куску по-разному. Заход кодировщика идёт одной непрерывной лентой, и
            # подгонка по такой голове вносила в неё скачок на 1-3 кадра; приёмник зовёт это
            # ``Parsed buffers not in DTS sequence`` и бросает показ (живой замер: 13 стыков
            # с меткой назад из 41 и 18 его перезаходов).
            mixed = state.run / f"{MIXED_PREFIX}{slot}.ts"
            if merge(better, path, mixed):
                source, how = mixed, "склейка"
            elif size and size <= state.cap:
                # Склейки нет: перекод уехал бы со своим звуком, на своей сетке AAC, а это
                # дыра на обоих стыках куска. Копия тут меньшее зло, пока влезает в потолок.
                source, how = path, "копия"
            else:
                source, how = better, "перекод"
        # Последний гейт стоит после склейки: только здесь известен вес ровно того
        # файла, который получит приёмник. Обе его части могут влезать по отдельности,
        # а готовый MPEG-TS - выйти за потолок из-за звука и накладных расходов.
        # Тогда голое видео перекода безопаснее; если не влезло и оно, наружу не
        # выходит ничего. Так же здесь остаётся тяжёлая копия, которую предохранитель
        # ожидания отпустил после срыва кодировщика.
        try:
            oversized = source.stat().st_size > state.cap
        except OSError:
            oversized = False
        if oversized and how == "склейка" and better is not None:
            source.unlink(missing_ok=True)
            try:
                safe_recode = better.stat().st_size <= state.cap
            except OSError:
                safe_recode = False
            if safe_recode:
                source, how = better, "перекод"
                oversized = False
        # Наружу такой кусок отдавать нельзя, но и вставать на нём навсегда нельзя: он
        # детерминирован, и встреча с ним повторялась бы каждый прогон. Поэтому сначала
        # одна попытка ужать кусок прямо сейчас (:attr:`shrink`) - перекод под потолок
        # ложится в spare, и наружу идёт его картинка со звуком копии
        # (:func:`_shrunk_out`): ужатие - это второй прогон ffmpeg над тем же местом, и
        # звук он приносит свой, на своей сетке AAC.
        #
        # ⚠️ Зовётся этот исход «ужатие», а не «перекод», и это не синоним. «Перекод» -
        # это готовый кусок кодировщика, у которого склейка со звуком копии НЕ ВЫШЛА, то
        # есть заявка на разбор стыка (:func:`torrcast.adapters.recode.note._note`). У ужатия
        # своя запись в журнале, потому что и склеивает оно своё: не голову захода
        # кодировщика, а единственное место, которое сам же и пересобрал. Пока оба звались
        # одним словом, каждый ужатый кусок печатал «склейка не вышла, стык под вопросом»:
        # на ровной сетке это 818 ложных заявок на разбор за фильм (TC-693).
        shrunk = oversized and state.shrink is not None and state.shrink(slot, size)
        if shrunk and better is not None:
            source = _shrunk_out(
                state.run,
                slot,
                path,
                better,
                state.cap,
                merge=merge,
                shift_of=shift_of,
                keyless=keyless,
            )
            how = "ужатие"
            try:
                oversized = source.stat().st_size > state.cap
            except OSError:
                oversized = True
        if oversized:
            if how == "склейка":
                source.unlink(missing_ok=True)
            if state.shrink is not None:
                # Ужать не вышло - честный пропуск: кусок не отдаём никому, но и
                # не стоим на нём. Пропуск - тоже решение выкладки, и край двигает
                # именно оно: иначе это место встречало бы каждый следующий прогон,
                # а его запрос крутил бы перепаковку вечно. Приёмнику про пропуск
                # отвечает показ (:attr:`Feed.skipped`), одной строкой и один раз.
                path.unlink(missing_ok=True)
                if better is not None:
                    better.unlink(missing_ok=True)
                state.edge = max(state.edge, slot)
                continue
            break
        moved = False
        with contextlib.suppress(OSError):
            os.replace(source, state.out / segment_name(slot))
            # Край двигает только состоявшееся переименование: «выложил» - это факт
            # этой строки, а не наличие файла в каталоге (:attr:`edge`).
            state.edge = max(state.edge, slot)
            moved = True
        # Выложили одно из трёх - остальные две копии этого места больше не нужны
        # никому: tmpfs не резиновая, а лишний файл в каталоге перекода ещё и выглядел
        # бы для кодировщика готовым куском (:meth:`torrcast.adapters.recode.recoder.Recoder.ready`).
        if moved and source is not path:
            path.unlink(missing_ok=True)
        if moved and better is not None and source is not better:
            better.unlink(missing_ok=True)
        if moved and state.told is not None:
            with contextlib.suppress(Exception):
                state.told(slot, how)
