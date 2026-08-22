"""Что ложится на диск от точечного перекода: его картинка со звуком копии.

Зовёт это заход прогрева (:func:`torrcast.usecases.warm.run._run`) на каждом точечном куске.
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.merge_tracks import merge_tracks
from torrcast.adapters.stream_pack.timeline_shift import timeline_shift
from torrcast.domain.hls_settings import MIXED_PREFIX
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def spot_out(
    slot: int,
    laid: Path,
    copy: Path,
    cap: int,
    *,
    merge: Callable[..., bool] = merge_tracks,
    shift_of: Callable[[Path, Path], float | None] = timeline_shift,
) -> bool:
    """Заменить уложенный точечный перекод склейкой его картинки со звуком копии.

    🔴 Точечный перекод - ОТДЕЛЬНЫЙ прогон ffmpeg на один кусок, и звук он приносит свой.
    Кадровая сетка AAC отсчитывается от ``-ss`` прогона, поэтому у соседей по каталогу
    сетки сдвинуты друг относительно друга на произвольную долю кадра, и на каждом стыке
    звук рвётся. Ровно та беда, ради которой написаны
    :func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks` и
    :func:`torrcast.adapters.stream_pack._shrunk_out._shrunk_out`, только приходит она не с головы
    захода кодировщика и не с краёв ужатого места, а с КАЖДОГО стыка на диске: на
    замеренной картине точечными оказались 813 кусков из 853.

    Замер на уложенном каталоге двухчасовой картины (кадр AAC 48 кГц = 1920 тиков 90 кГц):
    у кусков, уложенных копией одного прогона, фаза сетки одна на всех - 540 тиков,
    преролл звука 65.0-82.7 мс, стык 0.0 мс; у точечных перекодов фаза своя у каждого
    (270, 690, 1170, 330, 810, 1230), преролл ровно один кадр - 21.1 мс, - а стык
    **47.3-54.7 мс**. Приёмник платит за такой стык не миллисекундами: он пишет
    ``DEMUXER_UNDERFLOW`` по звуку и гасит конвейер (замер того же стыка у ужатия на
    месте - 4.1 и 4.3 с потерянной плёнки против нуля со склейкой).

    Склеивать есть с чем и есть чем: под точечным перекодом лежит копия этого же места
    (:func:`torrcast.usecases.warm.lay_heavy._lay_heavy`) - её звук и есть тот непрерывный
    поток, что уехал в соседние куски. Склейка - переупаковка без единого перекодирования.

    ``False`` - склейка не вышла или не влезла в ``cap``; на месте остаётся голый перекод,
    как лежал раньше. Потолок проверяется здесь же, потому что решение одно: кусок тяжелее
    потолка приёмника показ с диска не берёт вовсе
    (:meth:`torrcast.usecases.warm.vault.Vault.slots`), и точечная работа пропала бы зря.

    ``merge`` и ``shift_of`` приезжают доводами: оба поднимают ffmpeg и ffprobe на
    настоящих кусках, а здесь меряется решение - что именно остаётся лежать на диске.
    """
    mixed = laid.with_name(f"{MIXED_PREFIX}{laid.name}")
    if not merge(laid, copy, mixed, shift=shift_of(copy, laid) or 0.0):
        mixed.unlink(missing_ok=True)
        journal().mark("склейка точечного не вышла", слот=slot)
        return False
    weight = -1
    with contextlib.suppress(OSError):
        weight = mixed.stat().st_size
    if not 0 < weight <= cap:
        mixed.unlink(missing_ok=True)
        journal().mark("склейка точечного не влезла", слот=slot, вес=weight, потолок=cap)
        return False
    try:
        os.replace(mixed, laid)
    except OSError:
        mixed.unlink(missing_ok=True)
        return False
    return True
