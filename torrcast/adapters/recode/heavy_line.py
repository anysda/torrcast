"""Строка старта кодировщика: сколько кусков он берёт и по какой мерке они взяты.

Печатает её подъём кодировщика (:meth:`Recoder.start`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

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
    marks = " и ".join(
        mark
        for mark in (
            f"битрейт от {state.threshold:.0f} Мбит/с" if heavy else "",
            f"вес куска выше {state.cap / 1e6:.0f} МБ" if bulky else "",
        )
        if mark
    )
    return (
        f"кусков на перекод {len(taken)} из {state.grid.count} "
        f"({share * 100:.0f}% фильма, {marks}) - "
        f"перекодирую заранее не выше {state.encode.mbit:.0f} Мбит/с"
    )
