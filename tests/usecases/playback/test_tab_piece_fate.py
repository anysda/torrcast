"""Прогрев и показ одинаково решают судьбу куска между целью сетки вкладки и её пределом.

Кусок 28-80 МБ вкладка играет копией (:data:`torrcast.domain.browser_profile.BROWSER`).
Решают о нём трое, и все обязаны читать один предел: уборка прогретого
(:func:`torrcast.usecases.warm.trim.trim`), счёт прогретого запаса
(:attr:`torrcast.usecases.warm.warmer.Warmer.warmed`) и раздача с диска
(:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`). Разойдись они - и прогрев либо
стирает то, что показ отдал бы, либо зовёт запасом то, что показ не возьмёт.
"""

from __future__ import annotations

from pathlib import Path

from tests.usecases.playback.test__tract import _config, _Cutting
from tests.usecases.playback.world import grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.android_tv_profile import ANDROID_TV
from torrcast.domain.browser_profile import BROWSER
from torrcast.domain.profile import Profile
from torrcast.usecases.playback._tract import _tract

#: Кусок тяжелее цели сетки вкладки (28 МБ) и легче её предела (80 МБ).
_PIECE = 50_000_000
_SLOT = 3


def _twice(tmp_path: Path, profile: Profile) -> tuple[Path, float, Path | None]:
    """Прогретый кусок на диске, затем второй показ того же: уборка, счёт и раздача."""
    out = hls_dir(str(tmp_path / "hls"))
    config = _config(tmp_path)
    said = config, "http://ts", 0, "кино", out, grid(), None, 0.0, 8.0, False, _Cutting()
    _recoder, warmer, _feed, server, _receiver = _tract(*said, profile=profile)
    assert warmer is not None
    warmer.vault.open()
    piece = warmer.vault.path(_SLOT)
    with piece.open("wb") as laid:
        laid.truncate(_PIECE)
    server.stop()
    _recoder, warmer, feed, server, _receiver = _tract(*said, profile=profile)
    try:
        assert warmer is not None
        return piece, warmer.warmed, feed._warm(_SLOT) if piece.exists() else None
    finally:
        server.stop()


def test_the_tab_keeps_counts_and_serves_a_piece_under_its_limit(tmp_path: Path) -> None:
    """50 МБ вкладке - копия: уборка его не стирает, счёт берёт, раздача отдаёт с диска."""
    piece, warmed, served = _twice(tmp_path, BROWSER)

    assert piece.exists(), "уборка прогретого стёрла кусок, который вкладка играет копией"
    assert warmed == grid().span(_SLOT), "прогрев не считает запасом кусок, который отдаст показ"
    assert served == piece, "раздача не отдаёт прогретый кусок, который прогрев сохранил"


def test_a_tv_drops_the_same_piece_on_every_side(tmp_path: Path) -> None:
    """Приставке тот же кусок тяжелее предела: его нет ни на диске, ни в запасе, ни в раздаче."""
    assert ANDROID_TV.segment_limit < _PIECE

    piece, warmed, served = _twice(tmp_path, ANDROID_TV)

    assert (piece.exists(), warmed, served) == (False, 0.0, None)
