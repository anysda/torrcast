"""Завод раздачи упакованного по http: каталог, серт и лента показа.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) под именем ``HlsServer``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from torrcast.usecases.feed_pack.feed import Feed
from torrcast.usecases.playback.stream_server import StreamServer


class StreamServers(Protocol):
    """Чем показ поднимает свою раздачу - и ничего сверх того."""

    def __call__(
        self,
        root: Path,
        cert: str = "",
        key: str = "",
        *,
        port: int = ...,
        tls: bool = ...,
        feed: Feed | None = ...,
        warm_recodes: set[int] = ...,
    ) -> StreamServer:
        """Раздача на время показа: гаснет вместе с ним, что бы ни случилось."""
