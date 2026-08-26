"""Общий заголовок показа доезжает до приёмника и тогда, когда куски идут с диска."""

from __future__ import annotations

from typing import TYPE_CHECKING

from tests.usecases.feed_pack.world import feed, grid, tract, vault
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path

    from tests.usecases.feed_pack.world import FakeVault


def _box(name: bytes, body: bytes = b"") -> bytes:
    return (len(body) + 8).to_bytes(4, "big") + name + body


def _warm(where: FakeVault, slot: int, mark: bytes) -> Path:
    """Прогретый кусок CMAF со своим заголовком - такой, каким его кладёт прогрев."""
    piece = where.path(slot)
    piece.write_bytes(_box(b"ftyp", b"cmfc") + _box(b"moov", mark) + _box(b"moof", "м".encode()))
    return piece


def test_a_show_running_off_the_disk_still_gets_its_header(tmp_path: Path) -> None:
    """Фильм прогрет, источник мёртв, живая упаковка не выложит ни куска - заголовок есть.

    🔴 Это и есть обещанный продуктом досмотр без сети. Без заголовка приставка куски
    качает, а разбор не начинает вовсе: живой замер - 32 скачанных куска, ноль картинки,
    позиция 0:00:00.
    """
    tract()
    warm = vault(tmp_path, container=FMP4)
    _warm(warm, 2, "прогретый".encode())
    show = feed(tmp_path, grid=grid(), container=FMP4, vault=warm, wait=1.0)

    head = show.init()

    assert head == show.out / "init.mp4", "показ с диска остался без заголовка"
    body = head.read_bytes()
    assert body[4:8] == b"ftyp" and "прогретый".encode() in body
    assert b"moof" not in body, "в заголовок уехали данные куска"


def test_the_header_of_the_live_run_is_the_one_that_stays(tmp_path: Path) -> None:
    """Свой заголовок упаковки прогретым не переписывается: приёмник читает его один раз."""
    tract()
    warm = vault(tmp_path, container=FMP4)
    _warm(warm, 0, "прогретый".encode())
    show = feed(tmp_path, grid=grid(), container=FMP4, vault=warm, wait=1.0)
    (show.out / "init.mp4").write_bytes("живой".encode())

    assert show.init() == show.out / "init.mp4"
    assert (show.out / "init.mp4").read_bytes() == "живой".encode()


def test_the_previous_container_is_not_asked_for_a_header(tmp_path: Path) -> None:
    """У прежнего контейнера общего заголовка нет и в манифесте - там и брать нечего."""
    tract()
    warm = vault(tmp_path)
    warm.path(0).write_bytes(b"\x47" + b"x" * 1023)
    show = feed(tmp_path, grid=grid(), vault=warm, wait=1.0)

    assert show.init() is None
    assert not (show.out / "init.mp4").exists()


def test_an_empty_vault_leaves_the_show_without_a_header(tmp_path: Path) -> None:
    """Выдумывать заголовок неоткуда: прогретого нет - и показ честно отвечает пустотой."""
    tract()
    show = feed(tmp_path, grid=grid(), container=FMP4, vault=vault(tmp_path, FMP4), wait=1.0)

    assert show.init() is None
    assert not (show.out / "init.mp4").exists()
