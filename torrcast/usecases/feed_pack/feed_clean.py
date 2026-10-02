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
    Поэтому кодировщик тяжёлых кусков гасится, а хранилище прогрева отцепляется: в нём копии.
    Сам прогрев на такой ленте не поднимается (:func:`torrcast.usecases.playback._play._play`
    пускает его, только пока лента читает хранилище): сверка идёт в ``begin``, до старта.
    Кодировщик ставится в ту же скорость, что ужатие на месте
    (:func:`torrcast.usecases.feed_pack.feed_shrink._shrink`): оба потолка приёмника
    считает одно место.

    Ровная сетка по карте опорных кадров (``on_keys``) сюда не заходит: карту с не-IDR
    входами отвергает её же сторож, и принятая карта - уже ответ. Не сверилось - показ
    идёт прежним путём.
    """
    if not _copying(state) or _state.opens_clean(state.source, want) is not False:
        return False
    mbit = _switch(state, state.grid.slot_at(want))
    journal().mark("вход не IDR", закладка=round(want, 3), мбит=mbit)
    return True


def _recode_shelf(state: _State, slot: int) -> bool:
    """Перевести показ на сплошной перекод, если в голову ``slot`` с полки вкладке не войти.

    🔴 Голова с полки обходит сверку закладки (:func:`_recode_whole`): показ отдаёт кусок,
    нарезанный прогревом из копии, а у BD-AVC он начинается I-срезом без IDR с MMCO за ним.
    Живой замер на «Интерстелларе» с закладки 5348.469, голова v534 на полке: экран «Поток
    потерян» в четырёх продолжениях из четырёх. Сверка тут локальная, по куску на диске
    (:func:`torrcast.adapters.stream_pack.piece_opens.piece_opens`), раздачу не трогает.
    Кусок ещё не лёг или не сверился - голова идёт прежним путём.
    """
    if not _copying(state) or state.vault is None:
        return False
    piece = state.vault.path(slot)
    if not piece.exists() or _state.piece_opens(piece) is not False:
        return False
    journal().mark("голова с полки не IDR", слот=slot, мбит=_switch(state, slot))
    return True


def _copying(state: _State) -> bool:
    """Лента копирует по ровной сетке и может уйти в перекод: кодировщик есть, сплошного нет."""
    return state.recoder is not None and state.encode is None and not state.grid.on_keys


def _switch(state: _State, slot: int) -> float:
    """Сплошной перекод с ``slot`` до конца показа, кодировщик и хранилище копий отцеплены.

    Ответ - скорость перекода в Мбит/с, для журнала.
    """
    recoder = state.recoder
    assert recoder is not None  # спрашивали :func:`_copying`
    encode = recoder.fit(state.grid.span(slot), recoder.pace.table()[-1][0])
    state.encode = encode
    recoder.stop()
    state.recoder = None
    state.vault = None
    return round(encode.mbit, 2)
