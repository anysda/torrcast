from torrcast import InfraError as InfraError
from torrcast.state import Config as Config
from torrcast.state import Entry as Entry
from torrcast.stream import PROBE_TIMEOUT as PROBE_TIMEOUT
from torrcast.stream import TorrServer as TorrServer

__all__ = [
    "PROBE_TIMEOUT",
    "Config",
    "Entry",
    "InfraError",
    "TorrServer",
    "_cache_reserve",
]

def _cache_reserve(config: Config, entry: Entry) -> str: ...
