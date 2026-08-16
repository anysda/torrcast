from functools import partial as partial

from torrcast import InfraError as InfraError
from torrcast import trace as trace
from torrcast.cast import Receiver as Receiver
from torrcast.profile import Profile as Profile
from torrcast.profile import trace_thresholds as trace_thresholds
from torrcast.state import Config as Config
from torrcast.state import Entry as Entry
from torrcast.state import State as State
from torrcast.stream import Supply as Supply
from torrcast.stream import TorrServer as TorrServer
from torrcast.usecases.episode_duration import _duration as _duration
from torrcast.usecases.start_clock import _Clock as _Clock
from torrcast.usecases.torrents import _own_torrent as _own_torrent
from torrcast.usecases.watch import Watch as Watch

__all__ = [
    "WORKER_META",
    "Config",
    "Entry",
    "InfraError",
    "Profile",
    "Receiver",
    "State",
    "Supply",
    "TorrServer",
    "Watch",
    "_Clock",
    "_duration",
    "_following",
    "_own_torrent",
    "_worker_loop",
    "partial",
    "trace",
    "trace_thresholds",
]

WORKER_META: float

def _worker_loop(
    config: Config,
    key: str,
    torrserver: TorrServer,
    receiver: Receiver,
    supply: Supply,
    mine: list[str],
    profile: Profile,
) -> int: ...
def _following(key: str) -> Entry | None: ...
