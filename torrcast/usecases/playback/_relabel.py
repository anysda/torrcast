"""Раздача, которой можно назвать другое хранилище прогретых кусков.

Называет его пересборка сетки по концу картинки
(:class:`torrcast.usecases.playback._ending._Ending`).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class _Relabel(Protocol):
    """Раздача, которая подписывает в следе, откуда отдан кусок: с прогрева или из упаковки.

    Отдельно от :class:`torrcast.usecases.playback.stream_server.StreamServer`: подпись -
    свойство боевой раздачи, у подделок стенда её нет и спрашивать незачем.
    """

    def relabel(self, warm_recodes: set[int]) -> None:
        """Подписывать прогретыми куски из ``warm_recodes``."""
