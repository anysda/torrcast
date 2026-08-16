import contextlib as contextlib
import time as time

from torrcast import trace as trace
from torrcast.commands import Args
from torrcast.domain.exit_codes import EXIT_OK as EXIT_OK

__all__ = ["EXIT_OK", "Args", "_cmd_log", "_since_seconds", "contextlib", "time", "trace"]

def _cmd_log(args: Args) -> int: ...
def _since_seconds(since: str | None) -> float: ...
