import contextlib as contextlib
from collections.abc import Sequence as Sequence

from torrcast import TorrcastError as TorrcastError
from torrcast.domain.torrent_hash import _BTIH as _BTIH
from torrcast.domain.torrent_hash import _torrent_hash as _torrent_hash
from torrcast.state import Config as Config
from torrcast.state import State as State
from torrcast.stream import PROBE_TIMEOUT as PROBE_TIMEOUT
from torrcast.stream import TorrServer as TorrServer
from torrcast.stream import unit_active as unit_active

__all__ = [
    "PROBE_TIMEOUT",
    "_BTIH",
    "Config",
    "Sequence",
    "State",
    "TorrcastError",
    "TorrServer",
    "_held_by_show",
    "_own_torrent",
    "_release_orphans",
    "_release_torrents",
    "_torrent_hash",
    "contextlib",
    "unit_active",
]

def _release_torrents(config: Config, hashes: Sequence[str]) -> list[str]: ...
def _own_torrent(key: str, torrent_hash: str) -> None: ...
def _release_orphans(config: Config) -> None: ...
def _held_by_show(torrent_hash: str) -> bool: ...
