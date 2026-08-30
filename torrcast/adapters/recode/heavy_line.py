"""Строка старта кодировщика: сколько кусков он берёт и по какой мерке они взяты.

Печатает её подъём кодировщика (:meth:`Recoder.start`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


def _heavy_line(state: _State) -> str:
    """Что кодировщик берёт на перекод и по какой мерке он это выбрал.

    Мерки две и они не совпадают (:func:`torrcast.adapters.recode.targets._targets`):
    битрейт куска и вес его копии. Строка называет ту, которая сработала, - обе, если
    сработали обе. Замер на приставке: увесистыми выходили 741 кусок из 741, тогда как
    порога битрейта релиз не переходил ни разу, и названная не та мерка уводит разбор
    в битрейт релиза, где ничего и не было.
    """
    heavy = state.weights.heavy(state.threshold)
    bulky = state.weights.bulky(state.grid, state.cap)
    taken = state.targets
    share = sum(state.grid.span(slot) for slot in taken) / max(state.grid.duration, 1.0)
    marks = f" {phrase('recode.and')} ".join(
        mark
        for mark in (
            phrase("recode.bitrate_from", mbit=f"{state.threshold:.0f}") if heavy else "",
            phrase("recode.piece_weight_above", mb=f"{state.cap / 1e6:.0f}") if bulky else "",
        )
        if mark
    )
    return phrase(
        "recode.pieces_to_recode",
        count=len(taken),
        total=state.grid.count,
        share=f"{share * 100:.0f}",
        marks=marks,
        ceiling=f"{state.encode.mbit:.0f}",
    )
