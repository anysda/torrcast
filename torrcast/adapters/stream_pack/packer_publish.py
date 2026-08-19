"""Выкладка дописанного наружу: переименование, склейка со звуком копии и потолок веса.

Зовёт её :meth:`torrcast.adapters.stream_pack.packer.Packer.publish`, и только он.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack._segment_files import _names
from torrcast.adapters.stream_pack.merge_tracks import merge_tracks
from torrcast.adapters.stream_pack.timeline_shift import timeline_shift
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.domain.hls_settings import MIXED_PREFIX

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
) -> None:
    """Выложить наружу куски, которые ffmpeg уже дописал.

    Дописан тот, за которым появился следующий: сегментный муксер открывает новый
    файл ровно тогда, когда закрыл прошлый. Последний кусок такого соседа не получит
    никогда, поэтому за него отвечает отдельный признак (:meth:`Packer.finished`).
    Докатка (номер меньше ``first``) не выкладывается никогда — она короче своего
    места в манифесте и под её именем может лежать честный сегмент прошлого прогона.

    Признак «прогон дочитал вход» приходит доводом, а не спрашивается у класса: подменяют
    его наследники прогона на стендах показа, а импортировать сюда сам класс нельзя -
    выкладка живёт внутри него.

    Тем же доводом приезжают ``merge`` (склейка картинки перекода со звуком копии) и
    ``shift_of`` (сдвиг ленты между ними): обе поднимают ffmpeg и ffprobe на настоящих
    кусках, а здесь меряется РЕШЕНИЕ выкладки - что уходит наружу, что выбрасывается и
    куда встаёт край.
    """
    slots = sorted(s for s in map(segment_slot, _names(state.run)) if s >= 0)
    if not slots:
        return
    # Прогон дочитал вход до конца - дописан и последний кусок (:meth:`finished`).
    # Любой другой исход (жив, убит, оборвался) последний кусок дописанным не делает.
    done = slots if finished() else slots[:-1]
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
        source, how = path, "копия"
        if better is not None and better.exists():
            # Наружу идёт картинка перекода со звуком копии (:func:`merge_tracks`):
            # звук показа обязан остаться одним непрерывным потоком, а сама
            # картинка - лечь на ленту ЭТОГО прогона (:func:`timeline_shift`).
            mixed = state.run / f"{MIXED_PREFIX}{slot}.ts"
            shift = shift_of(path, better)
            if merge(better, path, mixed, shift=shift or 0.0):
                source, how = mixed, "склейка"
            elif shift and size and size <= state.cap:
                # Лента прогона сдвинута, а склейки нет: перекод как есть - это
                # гарантированный разрыв на кадр, и копия своего же прогона
                # тут меньшее зло. Но только пока она не тяжелее потолка: кусок,
                # который приёмник не доигрывает вовсе, хуже любого стыка.
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
        # Наружу такой кусок отдавать нельзя, но и вставать на нём навсегда нельзя:
        # прежний ``break`` тут не двигал край и не удалял копию, всё за ней копилось
        # в памяти до потолка несданного, потолок гасил прогон, запрос приёмника
        # поднимал его заново - и круг повторялся, потому что тяжёлый кусок
        # детерминирован. Поэтому сначала одна попытка ужать кусок прямо сейчас
        # (:attr:`shrink`) - перекод под потолок ложится в spare, и наружу идёт он,
        # как есть: его звук - та же дорожка AAC, что у копии.
        shrunk = oversized and state.shrink is not None and state.shrink(slot, size)
        if shrunk and better is not None:
            try:
                oversized = better.stat().st_size > state.cap
            except OSError:
                oversized = True
            if not oversized:
                source, how = better, "перекод"
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
