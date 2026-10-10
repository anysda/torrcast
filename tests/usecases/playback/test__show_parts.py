"""Зеркало частей показа: кодировщик и прогрев собираются на той сетке, что им назвали."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from tests.usecases.playback.world import grid
from torrcast.adapters.recode.recoder import Recoder
from torrcast.adapters.recode.whole_encode import whole_encode
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.config import Config
from torrcast.usecases.playback._show_parts import _show_parts

if TYPE_CHECKING:
    from pathlib import Path


def _config(tmp_path: Path) -> Config:
    return Config(recode=True, warm=True, warm_dir=str(tmp_path / "warm"), hls_port=0)


def test_both_parts_stand_on_the_named_grid(tmp_path: Path) -> None:
    """Пересборка по концу картинки называет новую сетку: оба участника обязаны её взять."""
    out = hls_dir(str(tmp_path / "hls"))
    lines = grid(295.0)

    recoder, warmer = _show_parts(
        _config(tmp_path), "http://ts", 0, "кино", out, lines, None, 0.0, 8.0
    )

    assert recoder is not None and cast(Recoder, recoder).grid is lines
    assert warmer is not None and warmer.grid is lines


def test_a_whole_recode_has_no_spot_recoder(tmp_path: Path) -> None:
    out = hls_dir(str(tmp_path / "hls"))
    whole = whole_encode(9.0)

    recoder, _warmer = _show_parts(
        _config(tmp_path), "http://ts", 0, "кино", out, grid(), whole, 0.0, 8.0
    )

    assert recoder is None


def test_a_late_regrid_builds_no_second_warm_up(tmp_path: Path) -> None:
    """Поздний конец картинки: прогрев у показа уже идёт, второй на новой сетке не заводится."""
    out = hls_dir(str(tmp_path / "hls"))
    lines = grid(295.0)

    recoder, warmer = _show_parts(
        _config(tmp_path), "http://ts", 0, "кино", out, lines, None, 0.0, 8.0, warm=False
    )

    assert recoder is not None and cast(Recoder, recoder).grid is lines
    assert warmer is None
    assert not (tmp_path / "warm").exists() or not any((tmp_path / "warm").iterdir())
