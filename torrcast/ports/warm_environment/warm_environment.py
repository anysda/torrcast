"""Среда прогрева: часы, файловая операция и телеметрия."""

from pathlib import Path
from typing import Protocol

from torrcast.ports.feed_grid import FeedGrid
from torrcast.ports.json_value import JsonValue
from torrcast.ports.warm_environment.encode_plan import EncodePlan
from torrcast.ports.warm_environment.warm_packer import WarmPacker


class WarmEnvironment(Protocol):
    """Побочные эффекты, которыми сценарий прогрева сам не владеет."""

    def epoch(self) -> float: ...

    def monotonic(self) -> float: ...

    def sleep(self, seconds: float) -> None: ...

    def remove_tree(self, path: Path) -> None: ...

    def emit(self, event: str, *args: object, **facts: object) -> None: ...

    def mark(self, name: str, **facts: JsonValue) -> None: ...

    def segment_name(self, slot: int) -> str: ...
    def segment_slot(self, name: str) -> int: ...
    def hms(self, seconds: float) -> str: ...
    @property
    def packer_type(self) -> WarmPacker: ...
    def pack_command(
        self,
        source_url: str,
        audio_index: int,
        run_dir: str,
        grid: FeedGrid,
        slot: int,
        at: float,
        readrate: float = 1.0,
        burst: float = 0.0,
        encode: EncodePlan | None = None,
        until: int = -1,
    ) -> list[str]: ...
    def pack_start(self, source_url: str, at: float) -> float: ...

    audio_mbit: float
    max_segment_bytes: int
    ts_overhead: float
