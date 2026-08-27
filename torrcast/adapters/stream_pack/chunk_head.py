"""Заголовок того прогона, который сделал картинку этого куска.

Спрашивают его выкладка показа (:func:`torrcast.adapters.stream_pack._own_head._own_head`)
и склейка (:mod:`torrcast.adapters.stream_pack._shrunk_out`,
:mod:`torrcast.adapters.stream_pack._merged_out`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from torrcast.domain.head_name import head_name

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer_state import _State

#: Общий заголовок показа: его приёмник забирает по ``EXT-X-MAP`` и им настраивает декодер.
INIT: Final = "init.mp4"


def chunk_head(state: _State, slot: int, *, spare: bool) -> Path:
    """Чем описан кусок этого места: заголовок его прогона, а не показа вообще.

    🔴 Производителей картинки у показа двое - копия отдаёт битстрим исходника, кодировщик
    пишет свой, - и параметры декодера у них разные (замер в :func:`._own_head._own_head`).
    Поэтому «заголовок этого куска» - вопрос не про показ, а про прогон, и отвечать на него
    обязано ОДНО место: угаданный заголовок не роняет ни склейку, ни показ, он молча отдаёт
    мусор (код возврата ноль при 334 строках ошибок), и купленная им зелёная мера стоит
    подменённой картины.

    ``spare`` - чья картинка: прогона кодировщика (``True``) или своего прогона упаковки.

    Кодировщик кладёт свой заголовок рядом с каждым куском поимённо
    (:func:`torrcast.domain.head_name.head_name`), и это единственное, на что здесь можно
    опереться: заходов у него много, пресет торгуется по сроку, а ``ultrafast`` и
    ``veryfast`` дают РАЗНЫЕ параметры картинки. Не оказалось поимённого - остаётся общий
    заголовок каталога: там, где кодировщик поднимался одним заходом, он и есть его.

    ⚠️ Свой заголовок прогона упаковки ищется в двух местах, и это не перестраховка: первая
    же выкладка уносит его из каталога прогона наружу (:func:`._lay_out`), а звук копии
    нужен склейке и после этого.
    """
    if spare and state.spare is not None:
        beside = state.spare / head_name(slot)
        return beside if beside.exists() else state.spare / INIT
    own = state.run / INIT
    return own if own.exists() else state.out / INIT
