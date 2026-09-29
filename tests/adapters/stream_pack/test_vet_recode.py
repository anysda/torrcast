"""Перекод места перед склейкой: проба опорного кадра и сдвиг лент идут разом."""

from __future__ import annotations

import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

from torrcast.adapters.stream_pack.vet_recode import vet_recode

if TYPE_CHECKING:
    from pathlib import Path


def _slow(answer: Any) -> Any:
    def probe(*_paths: Path) -> Any:
        time.sleep(0.3)
        return answer

    return probe


def test_the_key_frame_and_the_shift_are_probed_at_once(tmp_path: Path) -> None:
    """Подряд два ffprobe стояли на пути первого кадра «Призрака»."""
    recode = tmp_path / "r.ts"
    recode.write_bytes(b"x")
    state: Any = SimpleNamespace(recode_shift=None)

    began = time.monotonic()
    vet_recode(state, 0, tmp_path / "c.ts", recode, _slow(False), _slow(0.04))

    assert time.monotonic() - began < 0.5
    assert (state.recode_shift, recode.exists()) == (0.04, True)


def test_a_keyless_recode_is_dropped_and_gives_the_run_no_shift(tmp_path: Path) -> None:
    recode = tmp_path / "r.ts"
    recode.write_bytes(b"x")
    state: Any = SimpleNamespace(recode_shift=None)

    vet_recode(state, 0, tmp_path / "c.ts", recode, _slow(True), _slow(0.04))

    assert (state.recode_shift, recode.exists()) == (None, False)


def test_a_measured_run_is_not_measured_again(tmp_path: Path) -> None:
    recode = tmp_path / "r.ts"
    recode.write_bytes(b"x")
    state: Any = SimpleNamespace(recode_shift=0.1)
    asked: list[Path] = []

    vet_recode(state, 3, tmp_path / "c.ts", recode, lambda _p: False, lambda *p: asked.append(p[0]))

    assert (state.recode_shift, asked) == (0.1, [])
