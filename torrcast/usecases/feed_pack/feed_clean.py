"""Показ с закладки, куда копией не войти: переход ленты на сплошной перекод."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


def _recode_whole(state: _State, want: float) -> bool:
    """Перевести показ на сплошной перекод, если копия с ``want`` не открывается чисто.

    🔴 Опорный кадр контейнера у BD-AVC с открытым GOP - I-срез без IDR, и кадры за ним
    ссылаются на картинки до него (:func:`torrcast.adapters.stream_pack.opens_clean.opens_clean`).
    С нуля такой файл играет, а с закладки вкладка отвечает ``PIPELINE_ERROR_DECODE`` на
    первом же куске, и hls.js по кругу просит те же места: живой замер на 5212 МБ с
    закладки 177.837 - ни одного кадра за 99 с, сплошной перекод - кадр через 0.28 с.

    Переход липкий на весь показ: стык перекода с копией рвётся так же, как вход копией.
    Поэтому уходят и кодировщик тяжёлых кусков, и прогретое хранилище - в нём лежат копии.
    Кодировщик ставится в ту же скорость, что ужатие на месте
    (:func:`torrcast.usecases.feed_pack.feed_shrink._shrink`): оба потолка приёмника
    считает одно место.

    Ровная сетка по карте опорных кадров (``on_keys``) сюда не заходит: карту с не-IDR
    входами отвергает её же сторож, и принятая карта - уже ответ. Не сверилось - показ
    идёт прежним путём.
    """
    recoder = state.recoder
    if recoder is None or state.encode is not None or state.grid.on_keys:
        return False
    if _state.opens_clean(state.source, want) is not False:
        return False
    slot = state.grid.slot_at(want)
    state.encode = recoder.fit(state.grid.span(slot), recoder.pace.table()[-1][0])
    recoder.stop()
    state.recoder = None
    state.vault = None
    journal().mark("вход не IDR", закладка=round(want, 3), мбит=round(state.encode.mbit, 2))
    return True
