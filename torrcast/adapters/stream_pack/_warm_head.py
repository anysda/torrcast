"""Заголовок куска, который ложится на постоянный склад: оттуда его читает приёмник.

Зовёт это заголовок своего прогона (:func:`.._own_head._own_head`), когда прогон кладёт
куски не чужой выкладке, а на диск для показа (:attr:`~.packer_state._State.outward`).
"""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.carried_head import carried_head
from torrcast.adapters.stream_pack.chunk_head import INIT, chunk_head
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.domain.head_name import head_name
from torrcast.domain.hls_settings import HEAD_PREFIX
from torrcast.domain.segment_suffix import segment_suffix

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer_state import _State


def _general(state: _State) -> bytes:
    """Общий заголовок склада: ровно его приёмник берёт по ``EXT-X-MAP``.

    Кладёт его туда первый же заход прогрева (:meth:`Packer.publish`), а называет
    приёмнику показ (:func:`torrcast.usecases.feed_pack.feed_head._head`). Значит голый
    кусок на складе описан именно им - и другого описания у голого куска нет.
    """
    try:
        return (state.out / INIT).read_bytes()
    except OSError:
        return b""


def _seam(state: _State, slot: int, now: bytes) -> None:
    """Сосед справа, уже лежащий на складе голым, тоже обязан ответить за себя.

    🔴 Без этого правка не даёт зрителю ничего, а только двигает беду на место вперёд.
    Прогрев кладёт фильм копией, а тяжёлые места приводит к перекоду ПОЗДНИМ отдельным
    заходом (:meth:`torrcast.usecases.warm.warmer.Warmer._spots_left`): к тому времени
    сосед справа давно лежит голым. Приставили заголовок точечного месту ``N`` - приёмник
    настроен им, и голое ``N+1`` он прочитает тем же, хотя закодировано оно копией.

    Поэтому соседу приставляется общий заголовок склада - тот самый, которым он и описан.
    Кусок, который уже несёт свой (:func:`carried_head`), не трогаем: он отвечает сам.
    """
    nxt = state.out / segment_name(slot + 1, state.container)
    general = _general(state)
    if not general or general == now or not nxt.exists() or carried_head(nxt):
        return
    # Имя на время подмены начинается не с ``v``: под ``v*`` склад считает прогретое
    # (:meth:`torrcast.usecases.warm.vault.Vault.slots`), и полуготовый файл там был бы
    # куском. Подмена атомарна - показ читает склад параллельно и всегда видит целое.
    tmp = nxt.with_name(f"{HEAD_PREFIX}{nxt.name}")
    try:
        tmp.write_bytes(general + nxt.read_bytes())
        os.replace(tmp, nxt)
    except OSError:
        with contextlib.suppress(OSError):
            tmp.unlink(missing_ok=True)


def _warm_head(state: _State, slot: int, source: Path) -> Path:
    """Прогретый кусок с верными параметрами декодера: свой заголовок впереди.

    Живой путь спрашивает «чем уехало предыдущее место» у своей же записи рядом с куском
    (:data:`~torrcast.domain.hls_settings.HEAD_SENT`). Складу такая запись не нужна и
    вредна: он переживает и снятие показа, и перемотку, а ответ лежит в самом соседе -
    голый кусок описан общим заголовком склада, кусок со своим заголовком описан им
    (:func:`carried_head`). Второй источник правды о том же тут только разъезжался бы.

    Ответ - что выкладывать: сам ``source``, когда заголовок этого прогона тот же, каким
    описан сосед слева (тогда приставлять нечего и незачем), или новый файл с заголовком
    впереди.
    """
    own = chunk_head(state, slot, spare=False)
    try:
        now = own.read_bytes()
    except OSError:  # заголовка у прогона нет - прогрев идёт как шёл
        return source
    if not now:
        return source
    was = carried_head(state.out / segment_name(slot - 1, state.container)) or _general(state)
    if not was or now == was:
        return source
    _seam(state, slot, now)
    headed = state.run / head_name(slot, segment_suffix(state.container))
    try:
        headed.write_bytes(now + source.read_bytes())
    except OSError:
        headed.unlink(missing_ok=True)
        return source
    return headed
