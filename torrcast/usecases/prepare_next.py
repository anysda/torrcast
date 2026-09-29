"""Build a dormant next-episode search at a torrent boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.usecases.prepared_next import PreparedNext

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.domain.config import Config
    from torrcast.domain.entry import Entry
    from torrcast.domain.profile import Profile
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.select.plan import Plan
    from torrcast.usecases.select_bench.bench import Bench


def prepare_next(
    config: Config,
    key: str,
    torrserver: TorrentEngine,
    profile: Profile,
    entry: Entry,
    target: tuple[int, int],
    circle: Callable[..., list[Plan]],
    stand: Callable[..., Bench],
) -> PreparedNext:
    """Keep a next-episode search dormant until the current credits approach."""
    return PreparedNext(config, key, torrserver, profile, entry, target, circle, stand)
