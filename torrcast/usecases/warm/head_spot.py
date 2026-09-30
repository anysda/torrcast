"""Тяжёлый кусок, с которого начнётся показ, - первым в работу прогрева."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _head_spot(state: _State) -> int | None:
    """Стартовый кусок, который прогрев обязан перекодировать раньше остального фильма.

    Тяжёлые места прогрев кладёт копией и перекодирует после всего фильма
    (:func:`torrcast.usecases.warm._warm_count._spots_left`), а копию тяжелее потолка
    показ не берёт (:func:`torrcast.usecases.feed_pack.feed_segment._warm`) и ждёт живой
    перекод. На стартовом куске следующей серии это и есть стык: копия легла за 11 с до
    конца серии, а первый кадр пришёл через 6.6 с после него - 11 с фильма живым
    перекодом. Метка перекода ставится после первого же захода (:func:`_run`), поэтому
    кусок берётся в работу один раз.

    Только у прогрева следующей серии (:attr:`ahead`): у текущей стартовый кусок живой показ
    уже отдал, и перекодировать его первым - пустая работа в самом тесном окне показа.

    При сплошном перекоде (:attr:`encode`) стартовый кусок - такой же перекод, и ждать
    цепочки ему нельзя тем же образом: зритель, перемотавший серию к концу, встречал стык
    без единого куска следующей (замер на HEVC: 3.2 с живого перекода старта после конца
    серии). Кусок лёг на полку - работа сделана.
    """
    head = state.began_at
    if not state.ahead or head in state.hopeless:
        return None  # у текущей серии этот кусок уже отдал живой показ
    if state.encode is not None:
        return None if state.vault.have(head) else head
    if state.spot_encode is None or head not in state.spots:
        return None
    return None if state.vault.spot(head).exists() else head
