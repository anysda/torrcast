"""Заголовок того прогона, который сделал картинку этого куска."""

from __future__ import annotations

from pathlib import Path

from tests.usecases.feed_pack.world import packer
from torrcast.adapters.stream_pack.chunk_head import INIT, chunk_head
from torrcast.adapters.stream_pack.packer_state import _State
from torrcast.domain.head_name import head_name
from torrcast.domain.segment_container import FMP4


def _state(tmp_path: Path, *, spare: bool) -> _State:
    keep = tmp_path / "spare"
    keep.mkdir(parents=True, exist_ok=True)
    return packer(tmp_path, container=FMP4, spare=keep if spare else None)


def test_the_picture_of_the_encoder_is_described_by_the_head_lying_beside_it(
    tmp_path: Path,
) -> None:
    """🔴 Заходов у кодировщика много, пресет торгуется по сроку - опереться можно только на имя."""
    state = _state(tmp_path, spare=True)
    assert state.spare is not None
    beside = state.spare / head_name(7)
    beside.write_bytes(b"own")
    (state.spare / INIT).write_bytes(b"shared")

    assert chunk_head(state, 7, spare=True) == beside


def test_without_a_head_by_name_the_common_one_of_that_catalogue_is_taken(tmp_path: Path) -> None:
    """Поимённого нет - берётся общий заголовок каталога: где заход был один, он и есть его."""
    state = _state(tmp_path, spare=True)
    assert state.spare is not None

    assert chunk_head(state, 7, spare=True) == state.spare / INIT


def test_the_sound_of_our_own_run_is_described_by_the_head_of_that_run(tmp_path: Path) -> None:
    """Звук приезжает из своего прогона упаковки, и заголовок у него свой."""
    state = _state(tmp_path, spare=True)
    (state.run / INIT).write_bytes(b"mine")

    assert chunk_head(state, 7, spare=False) == state.run / INIT


def test_the_head_carried_outside_by_the_first_publish_is_still_found(tmp_path: Path) -> None:
    """⚠️ Первая же выкладка уносит заголовок прогона наружу, а звук нужен склейке и после."""
    state = _state(tmp_path, spare=True)
    (state.out / INIT).write_bytes(b"mine")

    assert chunk_head(state, 7, spare=False) == state.out / INIT


def test_the_run_that_has_no_encoder_beside_it_answers_about_itself(tmp_path: Path) -> None:
    """У прогона кодировщика соседа нет вовсе - спрашивать о чужой картинке не у кого."""
    state = _state(tmp_path, spare=False)
    (state.run / INIT).write_bytes(b"mine")

    assert chunk_head(state, 7, spare=True) == state.run / INIT
