"""Чем шаг ``POST /api/search`` ищет выдачу: круг поиска консоли либо подделка в тесте."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Protocol

from torrcast.domain.config import Config
from torrcast.domain.profile import Profile
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan


class Search(Protocol):
    """Тот же круг поиска, что у показа; ``on_indexer`` - его шов превью (TC-1126)."""

    def __call__(
        self,
        config: Config,
        args: Args,
        progress: Progress,
        profile: Profile,
        /,
        *,
        on_indexer: Callable[[IndexerClient], None] | None = None,
    ) -> list[Plan]: ...


__all__ = ["Search"]
