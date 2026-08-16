from typing import TYPE_CHECKING as TYPE_CHECKING

from torrcast import trace as trace
from torrcast.commands import EXIT_OK as EXIT_OK
from torrcast.commands import Args
from torrcast.console import Progress as Progress
from torrcast.facts import Facts as Facts
from torrcast.parse import Picture as Picture
from torrcast.parse import slugify as slugify
from torrcast.parse import split_franchise_index as split_franchise_index
from torrcast.profile import detect as detect_profile
from torrcast.profile import tune as tune_profile
from torrcast.search import Prowlarr as Prowlarr
from torrcast.search import RawResult as RawResult
from torrcast.search import merge as merge
from torrcast.search import to_releases as to_releases
from torrcast.state import Entry as Entry
from torrcast.state import State as State
from torrcast.state import load_config as load_config
from torrcast.stream import TorrServer as TorrServer
from torrcast.stream import bitrate_mbit as bitrate_mbit
from torrcast.timing import mark as mark

__all__ = [
    "EXIT_OK",
    "TYPE_CHECKING",
    "Entry",
    "Facts",
    "Picture",
    "Progress",
    "Prowlarr",
    "RawResult",
    "State",
    "TorrServer",
    "_cmd_play",
    "_relayout",
    "_season_asked",
    "_titled_number",
    "bitrate_mbit",
    "detect_profile",
    "load_config",
    "mark",
    "merge",
    "season_reread",
    "slugify",
    "split_franchise_index",
    "to_releases",
    "trace",
    "tune_profile",
]

def _cmd_play(args: Args) -> int: ...
def _relayout(
    client: Prowlarr, query: str, name: str, index: int | None, progress: Progress
) -> tuple[str, str, int | None, list[RawResult]]: ...
def _titled_number(
    client: Prowlarr, query: str, name: str, raw: list[RawResult], progress: Progress
) -> tuple[list[RawResult], list[Picture], list[Picture]]: ...
def _season_asked(found: list[Picture], name: str, pictures: list[Picture]) -> bool: ...
def season_reread(
    args: Args, name: str, index: int | None, found: list[Picture], pictures: list[Picture]
) -> Args | None: ...
