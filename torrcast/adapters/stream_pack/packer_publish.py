"""Выкладка дописанного наружу: переименование, склейка со звуком копии и потолок веса.

Зовёт её :meth:`torrcast.adapters.stream_pack.packer.Packer.publish`, и только он.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack._merged_out import _merged_out
from torrcast.adapters.stream_pack._own_head import _own_head
from torrcast.adapters.stream_pack._segment_files import _names
from torrcast.adapters.stream_pack._shrunk_out import _shrunk_out
from torrcast.adapters.stream_pack.chunk_head import chunk_head
from torrcast.adapters.stream_pack.done_slots import done_slots
from torrcast.adapters.stream_pack.key_missing import key_missing
from torrcast.adapters.stream_pack.merge_tracks import merge_tracks
from torrcast.adapters.stream_pack.over_cap import over_cap
from torrcast.adapters.stream_pack.run_tape import run_tape
from torrcast.adapters.stream_pack.slot_place import slot_place
from torrcast.adapters.stream_pack.timeline_shift import timeline_shift
from torrcast.adapters.stream_pack.track_starts import track_starts
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
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
    starts_of: Callable[[str | Path], tuple[float, float]] = track_starts,
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
    ``shift_of`` (сдвиг ленты, нужный ужатию на месте), ``keyless`` (не начинается ли
    перекод БЕЗ опорного кадра) и ``starts_of`` (где на ленте стоят обе дорожки готовой
    склейки): все четверо поднимают ffmpeg и ffprobe на настоящих кусках,
    а здесь меряется РЕШЕНИЕ выкладки - что уходит наружу и куда встаёт край.
    """
    init = state.run / "init.mp4"
    if init.exists() and not (state.out / init.name).exists():
        with contextlib.suppress(OSError):
            os.replace(init, state.out / init.name)
    slots = sorted(s for s in map(segment_slot, _names(state.run)) if s >= 0)
    if not slots:
        return
    # Прогон дочитал вход до конца - дописан и последний кусок (:meth:`finished`).
    # Любой другой исход (жив, убит, оборвался) последний кусок дописанным не делает.
    done = done_slots(state, slots, finished())
    for slot in done:
        path = state.run / segment_name(slot, state.container)
        # Докатка и обрезок за ``-to`` короче своего места и наружу не выходят.
        if slot < state.first or 0 <= state.last < slot:
            path.unlink(missing_ok=True)
            continue
        # Кусок сейчас перекодируют - подождём его (:attr:`hold`). Дальше по списку не
        # идём: выложить следующий, оставив дыру, значит увести край за неё, и запрос
        # придержанного места выглядел бы для :meth:`Feed._steer` перемоткой назад.
        #
        # Спрашивающему отдаётся вес готовой копии: предсказание бывает неточным.
        size = 0
        with contextlib.suppress(OSError):
            size = path.stat().st_size
        if state.hold is not None and state.hold(slot, size):
            break
        # Перекодированный кусок этого же места лучше копии: то же разрешение и те же
        # метки, но битрейт, который приёмник тянет. Копия при этом выбрасывается.
        better = (
            state.spare / segment_name(slot, state.container) if state.spare is not None else None
        )
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
        # 🔴 "how" - внутренний ярлык, не надпись человеку: слово для показа берёт каталог.
        source, how = path, "copy"
        # Чем описаны обе половины будущей склейки: картинка приезжает от кодировщика,
        # звук - из своего прогона, и заголовки у них РАЗНЫЕ (:func:`chunk_head`).
        heads = (chunk_head(state, slot, spare=True), chunk_head(state, slot, spare=False))
        # Лента прогона меряется один раз, по первому же выложенному куску: на CMAF метка
        # куска - счётчик муксера, а не время фильма (:func:`run_tape`).
        if state.tape is None:
            state.tape = run_tape(state, slot, path, heads[1], starts_of)
        # Место этого слота на ленте картинки и на ленте звука: с ними сверяются обе дорожки
        # готовой склейки. Сетки у прогона может не быть (щупы и стенды), лента может быть ещё
        # не измерена - тогда сверять не с чем, и места не проверяют.
        want = slot_place(state, slot)
        if better is not None and better.exists():
            if state.recode_shift is None:
                state.recode_shift = shift_of(path, better) or 0.0
            source, how = _merged_out(
                state.run, slot, path, better, size, state.cap, want, state.container, heads,
                shift=state.recode_shift, merge=merge, starts_of=starts_of,
            )  # fmt: skip
        # Последний гейт стоит после склейки: только здесь известен вес ровно того
        # файла, который получит приёмник. Обе его части могут влезать по отдельности,
        # а готовый MPEG-TS - выйти за потолок из-за звука и накладных расходов.
        # Тогда голое видео перекода безопаснее; если не влезло и оно, наружу не
        # выходит ничего. Так же здесь остаётся тяжёлая копия, которую предохранитель
        # ожидания отпустил после срыва кодировщика.
        oversized = over_cap(source, state.cap)
        if oversized and how == "splice" and better is not None:
            source.unlink(missing_ok=True)
            try:
                safe_recode = better.stat().st_size <= state.cap
            except OSError:
                safe_recode = False
            if safe_recode:
                source, how = better, "recode"
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
        shrunk = state.shrink(slot, size) if oversized and state.shrink is not None else False
        if shrunk is None and better is not None:
            source, how, oversized = better, "recode", False
        elif shrunk and better is not None:
            # Место и обе мерки приёмника разом: каталог прогона, слот, копия, ужатое,
            # потолок веса и контейнер - расширение склейки выбирает муксер по нему.
            place = (state.run, slot, path, better, state.cap, want, state.container, heads)
            source = _shrunk_out(
                *place, merge=merge, shift_of=shift_of, keyless=keyless, starts_of=starts_of
            )
            how = "shrink"
            oversized = over_cap(source, state.cap, missing=True)
        if oversized:
            if how == "splice":
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
        # Параметры декодера у этого куска - его собственные (:func:`_own_head`).
        source = _own_head(state, slot, source, how)
        moved = False
        with contextlib.suppress(OSError):
            os.replace(source, state.out / segment_name(slot, state.container))
            # Край двигает только состоявшееся переименование: «выложил» - это факт
            # этой строки, а не наличие файла в каталоге (:attr:`edge`).
            state.edge = max(state.edge, slot)
            moved = True
        # Остальные копии места больше не нужны: лишний файл в каталоге перекода выглядел бы для
        # кодировщика готовым куском (:meth:`torrcast.adapters.recode.recoder.Recoder.ready`).
        if moved and source is not path:
            path.unlink(missing_ok=True)
        if moved and better is not None and source is not better:
            better.unlink(missing_ok=True)
        if moved and state.told is not None:
            with contextlib.suppress(Exception):
                state.told(slot, how)
