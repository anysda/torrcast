from torrcast.state import Entry as Entry
from torrcast.state import State as State
from torrcast.stream import probe as probe

__all__ = ["WORKER_DUR", "Entry", "State", "_duration", "probe"]

WORKER_DUR: float

def _duration(key: str, entry: Entry, source: str) -> Entry: ...
