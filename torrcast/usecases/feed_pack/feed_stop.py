"""Конец показа и его тихая пауза: гасим упаковку, каталог показа пустеет.

Зовёт отсюда сам показ (:mod:`torrcast.usecases.feed_pack.feed`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.hls_settings import PACK_DIR

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


def _rest(state: _State) -> bool:
    """Остаток фильма прогрет целиком — живую упаковку гасим; ``True`` — погасили.

    Держать её дальше значит тянуть из раздачи байты, которые уже лежат на диске, и
    отбирать полосу у прогрева головы. Это не конец показа: запрос куска, которого в
    прогретом нет, поднимет упаковку заново (:meth:`_steer`), как после паузы.
    """
    if state.vault is None or not state.lock.acquire(blocking=False):
        return False
    try:
        packer = state.packer
        if packer is None or packer.halted:
            return False
        packer.halt(reason=phrase("feed.rest_warmed_reason"))
        return True
    finally:
        state.lock.release()


def _stop(state: _State) -> None:
    """Показ окончен: упаковка гаснет, каталог показа пустеет.

    Флажок «картинка на экране» снимается ровно здесь и больше нигде: пока показ идёт,
    он и есть доказательство картинки для CLI, поэтому перезапуски
    упаковки (:meth:`restart`, перемотка) его не трогают. А после остановки это уже
    не доказательство, а пустой файл, который переживал `cast stop` в tmpfs.
    """
    # Закрыто насовсем: поток раздачи, спящий в segment() до двух минут, не должен
    # проснуться и поднять новый ffmpeg в каталог, который уже отдан следующей серии.
    state.fatal = state.fatal or phrase("feed.show_over")
    if state.recoder is not None:
        state.recoder.stop()
    with state.lock:
        if state.packer is not None:
            state.packer.stop()
    for junk in _state.segment_paths(state.out):
        junk.unlink(missing_ok=True)
    _state.remove_tree(state.out / PACK_DIR)
    _state.remove_tree(state.out / _state.RECODE_DIR)
    _state.forget_playing(state.out)
