import contextlib as contextlib
import signal as signal

from torrcast import TorrcastError as TorrcastError
from torrcast.cast import make_receiver as make_receiver
from torrcast.profile import detect as detect_profile
from torrcast.profile import tune as tune_profile
from torrcast.state import load_config as load_config
from torrcast.stream import PROBE_TIMEOUT as PROBE_TIMEOUT
from torrcast.stream import Supply as Supply
from torrcast.stream import TorrServer as TorrServer
from torrcast.timing import mark as mark
from torrcast.usecases.stopped import _on_term as _on_term
from torrcast.usecases.torrents import _own_torrent as _own_torrent
from torrcast.usecases.torrents import _release_torrents as _release_torrents
from torrcast.usecases.worker_loop import _worker_loop as _worker_loop

__all__ = [
    "Supply",
    "TorrcastError",
    "TorrServer",
    "_cmd_worker",
    "_on_term",
    "_own_torrent",
    "_release_torrents",
    "_worker_loop",
    "contextlib",
    "detect_profile",
    "make_receiver",
    "mark",
    "signal",
    "tune_profile",
]

def _cmd_worker(key: str) -> int: ...
