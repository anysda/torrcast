"""Заголовок прогретого куска: приёмник читает его со склада, мимо всякой выкладки."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import packer
from torrcast.adapters.stream_pack._warm_head import _warm_head
from torrcast.adapters.stream_pack.carried_head import carried_head
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.adapters.stream_pack.packer import Packer


def _box(kind: bytes, payload: bytes = b"") -> bytes:
    return struct.pack(">I", 8 + len(payload)) + kind + payload


def _head(mark: bytes) -> bytes:
    """Заголовок прогона: разница у копии и перекода ровно в визуальной записи."""
    return _box(b"ftyp", b"iso6") + _box(b"moov", mark * 50)


#: Общий заголовок склада (копия) и заголовок точечного перекода: они РАЗНЫЕ.
_GENERAL = _head(b"c")
_SPOT = _head(b"e")
#: Голый кусок сетки: ровно так прогрев и кладёт его на склад.
_BARE = _box(b"moof", b"x" * 40) + _box(b"mdat", b"y" * 90)


def _vault(root: Path, *, own: bytes | None = None) -> Packer:
    """Склад с общим заголовком и прогон поверх него; ``own`` - заголовок ЭТОГО прогона."""
    run = packer(root, container=FMP4, outward=True)
    (run.out / "init.mp4").write_bytes(_GENERAL)
    if own is not None:
        (run.run / "init.mp4").write_bytes(own)
    return run


def _piece(run: Packer, slot: int, body: bytes = _BARE) -> Path:
    """Кусок, лежащий на складе под своим слотом."""
    piece = run.out / f"v{slot}.m4s"
    piece.write_bytes(body)
    return piece


def test_a_copy_run_leaves_the_warmed_piece_exactly_as_it_was(tmp_path: Path) -> None:
    """Прогрев идёт копией, заголовок у него общий - приставлять нечего и незачем."""
    run = _vault(tmp_path)
    piece = _piece(run, 5)

    assert _warm_head(run, 5, piece) is piece


def test_a_piece_shrunk_by_the_warming_carries_the_head_of_its_own_run(tmp_path: Path) -> None:
    """Иначе приёмник настроит декодер общим заголовком, которым этот кусок не описан."""
    run = _vault(tmp_path, own=_SPOT)
    piece = _piece(run, 5)

    headed = _warm_head(run, 5, piece)

    assert headed != piece
    assert headed.read_bytes() == _SPOT + _BARE
    assert carried_head(headed) == _SPOT


def test_the_bare_neighbour_on_the_right_takes_the_general_head_back(tmp_path: Path) -> None:
    """🔴 Без этого беда не снята, а сдвинута на место вперёд: сосед закодирован копией."""
    run = _vault(tmp_path, own=_SPOT)
    piece = _piece(run, 5)
    nxt = _piece(run, 6)

    _warm_head(run, 5, piece)

    assert carried_head(nxt) == _GENERAL
    assert nxt.read_bytes() == _GENERAL + _BARE


def test_a_neighbour_that_already_answers_for_itself_is_not_touched(tmp_path: Path) -> None:
    """Кусок со своим заголовком описан им же - второй впереди сделал бы его мусором."""
    run = _vault(tmp_path, own=_SPOT)
    piece = _piece(run, 5)
    nxt = _piece(run, 6, _SPOT + _BARE)

    _warm_head(run, 5, piece)

    assert nxt.read_bytes() == _SPOT + _BARE


def test_the_head_of_the_place_before_is_asked_of_the_disk_not_of_the_run(tmp_path: Path) -> None:
    """Склад переживает и снятие показа, и перемотку, а память прогона - нет.

    Сосед слева уже уехал с тем же заголовком, каким описан этот кусок: декодер приёмника
    настроен верно, и приставлять второй такой же значит пересобирать его на ровном месте.
    """
    run = _vault(tmp_path, own=_SPOT)
    _piece(run, 4, _SPOT + _BARE)
    piece = _piece(run, 5)

    assert _warm_head(run, 5, piece) is piece


def test_a_run_without_any_head_warms_the_way_it_warmed_before(tmp_path: Path) -> None:
    """Заголовка нет ни у прогона, ни у склада - сказать про кусок нечего, и мы молчим."""
    run = packer(tmp_path, container=FMP4, outward=True)
    piece = _piece(run, 5)

    assert _warm_head(run, 5, piece) is piece
