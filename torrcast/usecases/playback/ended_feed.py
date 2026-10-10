"""Лента показа, чей конец картинки встаёт за упаковкой головы, а не до неё.

Собирает её медиатракт (:func:`torrcast.usecases.playback._tract._tract`), список у неё
берёт раздача (:class:`torrcast.adapters.http_server.hls_server.HlsServer`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from torrcast.usecases.feed_pack.feed import Feed


@dataclass(slots=True)
class EndedFeed(Feed):
    """Лента, у которой конец картинки ставится по готовности паспорта, без ожидания.

    🔴 Сетка до конца контейнера, а не картинки, оставила приставку на 2579.5 с из 2588.5
    («Отчаянные домохозяйки» s3, звук на 114 с длиннее картинки). Хвост файла холодной
    раздачи читается до 10 с, и ждать его - это столько же к старту: приёмник просит список
    первым же запросом LOAD, и первый кусок он просит только после списка. Поэтому список
    (``settle``) ставит конец, только если паспорт уже готов, а поздний паспорт ведут часы
    показа (``tick``, :meth:`sweep`): сетка меняется, когда упаковка дойдёт до расхождения.
    """

    settle: Callable[[], None] | None = None
    tick: Callable[[], None] | None = None

    def manifest(self, name: str = "index.m3u8") -> bytes:
        """Список кусков сразу; готовый паспорт успевает встать в него (``settle``)."""
        if self.settle is not None:
            self.settle()
        return Feed.manifest(self, name)

    def sweep(self) -> None:
        """Уборка ленты и поздний конец картинки, когда упаковка дошла до него (``tick``)."""
        Feed.sweep(self)
        if self.tick is not None:
            self.tick()

    def stop(self) -> None:
        """Показ окончен: поздний конец картинки сетку больше не трогает."""
        self.tick = None
        Feed.stop(self)
