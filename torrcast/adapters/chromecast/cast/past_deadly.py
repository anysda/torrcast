"""Откуда поднимать показ: с места смерти или уже ЗА куском, который его убивает.

Спрашивают это обе ветки подъёма - повтор LOAD и воскрешение погасшего показа."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_state import _State


def _past_deadly(rcv: _State, at: float) -> float:
    """Откуда поднимать показ: с места ``at`` или уже ЗА куском, который его убивает.

    Считает смерти по кускам. Пока их меньше :attr:`DEADLY_TRIES`, место подъёма
    остаётся тем же: показ, погасший от моргнувшей сети, обязан вернуться туда, где
    человек его смотрел. Набралось - кусок невоспроизводим, и возвращаться в него
    значит вернуться и за следующей смертью.

    ⚠️ Кусков два: считаем по тому, где погас показ, а прыгаем за тот, где давится
    декодер (:attr:`torrcast.domain.profile.Profile.start_buffer` впереди кадра). Счёт по цели
    врёт: ``at`` подрастает, сдвинутый ключ рвёт границу сетки не там, и смерти
    разъезжаются по двум счётчикам - перешагивание опоздает на круг восстановления.

    🔴 Замер на «Моане» 2016: приёмник умирал на одном и том же месте четыре раза, и
    каждый круг восстановления - три повтора LOAD, два нуджа, воскрешение - отдавал
    ему тот же кусок и получал тот же исход. За 5 мин 48 с позиция сдвинулась со
    125.4 на 127.8 с, показ кончился ``watched=false``. Ни одна ветка подъёма при этом
    не помнила, что здесь уже умирали: счётчики были у попыток, а не у места.

    Сетки не назвали (:attr:`next_cut`) - шагать некуда и считать нечего: без границ
    «тот же кусок» неотличим от «то же место», а прыгать на глазок мимо куска, длина
    которого неизвестна, - это тот же промах, только тише.
    """
    if rcv.next_cut is None:
        return at
    cut, dead = rcv.next_cut(at + rcv.profile.start_buffer), rcv.next_cut(at)
    died = rcv._deaths[dead] = rcv._deaths.get(dead, 0) + 1
    if died < rcv.DEADLY_TRIES:
        return at
    to = cut + rcv.CUT_SLACK
    print(
        phrase(
            "chromecast_talk.dying_on_one_chunk",
            count=died,
            gap=f"{to - at:.0f}",
            start=f"{at:.0f}",
            end=f"{to:.0f}",
        ),
        flush=True,
    )
    return to
