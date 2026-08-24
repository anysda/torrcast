"""Проверяет обработчик запросов приёмника: что он отдаёт, что режет и чем метит кусок."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from torrcast.adapters.http_server._handler import _ASSET_RE, _RANGE_RE, _TYPES, _Handler
from torrcast.domain.trace_sources import PACKED, WARMED


class _Supply:
    """Поставщик сегментов на две полки: упакованное сейчас и взятое с прогретого."""

    def __init__(self, out: Path, warm: Path) -> None:
        self.out = out
        self._warm = warm

    def manifest(self, name: str = "index.m3u8") -> bytes:
        return b"#EXTM3U\n"

    def init(self) -> Path | None:
        return self.out / "init.mp4"

    def segment(self, slot: int) -> Path | None:
        packed = self.out / f"v{slot}.ts"
        warmed = self._warm / f"v{slot}.ts"
        if packed.exists():
            return packed
        return warmed if warmed.exists() else None


def _handler(feed: _Supply | None = None, root: Path | None = None, span: str = "") -> _Handler:
    ready = cast(Any, object.__new__(_Handler))
    ready.headers = {"Range": span} if span else {}
    ready.feed = feed
    ready.root = root or Path()
    return cast(_Handler, ready)


@pytest.mark.parametrize("name", ["v0.ts", "v137.ts", "index.m3u8"])
def test_the_grid_of_the_show_is_served(name: str) -> None:
    assert _ASSET_RE.fullmatch(name), f"{name} - это манифест или сегмент сетки"


@pytest.mark.parametrize(
    "name", ["../state.json", "v1.ts/../../etc/passwd", "index.m3u8?x=1", "", "v.ts", "source.mp4"]
)
def test_nothing_but_the_grid_is_served(name: str) -> None:
    """Каталог наружу не открыт: имя вне сетки - 404, а не файл с диска."""
    assert not _ASSET_RE.fullmatch(name), f"{name} уехал бы наружу"


def test_the_content_types_are_the_ones_the_receiver_expects() -> None:
    """Chromecast разбирает манифест по типу ответа: чужой тип - LOAD ERROR без объяснений."""
    assert _TYPES[".m3u8"] == "application/vnd.apple.mpegurl"
    assert _TYPES[".ts"] == "video/mp2t"
    assert _TYPES[".m4s"] == "video/mp4"
    assert _TYPES[".mp4"] == "video/mp4"


@pytest.mark.parametrize(
    ("span", "size", "want"),
    [
        ("bytes=0-99", 1000, (0, 99)),
        ("bytes=100-", 1000, (100, 999)),
        ("bytes=-50", 1000, (950, 999)),
        ("bytes=0-100000", 1000, (0, 999)),
        ("bytes=2000-3000", 1000, ()),
        ("bytes=500-100", 1000, ()),
    ],
)
def test_the_receiver_asks_for_pieces_of_a_segment_by_range(
    span: str, size: int, want: tuple[int, ...]
) -> None:
    """Q70D переспрашивает куски диапазонами; хвост ``-50`` и открытый ``100-`` - тоже диапазоны.

    Диапазон за краем файла - не кусок, а 416: отдать вместо него весь файл значило бы
    соврать приёмнику про то, что он получил.
    """
    assert _handler(span=span)._range(size) == want


def test_a_request_without_a_range_gets_the_whole_piece() -> None:
    assert _handler()._range(1000) is None
    assert _handler(span="куски=0-9")._range(1000) is None, "чужой синтаксис диапазоном не считаем"
    assert _RANGE_RE.fullmatch("bytes=0-9"), "разбор диапазона держится на этом выражении"


def test_the_source_of_every_piece_is_remembered_for_the_trail(tmp_path: Path) -> None:
    """🔴 Показ идёт кусками ДВУХ производителей, и в следе обязано быть видно, чей это кусок.

    Без источника разбор «почему приёмник споткнулся вот здесь» упирается в то, что по
    записи нельзя сказать, сменился ли производитель ровно на этом месте.
    """
    out, warm = tmp_path / "out", tmp_path / "warm"
    out.mkdir()
    warm.mkdir()
    (out / "v1.ts").write_bytes("свежий".encode())
    (warm / "v2.ts").write_bytes("прогретый".encode())
    feed = _Supply(out, warm)

    packed = _handler(feed)
    assert packed._read("v1.ts") == "свежий".encode()
    assert packed._src == PACKED

    warmed = _handler(feed)
    assert warmed._read("v2.ts") == "прогретый".encode()
    assert warmed._src == WARMED

    assert _handler(feed)._read("v3.ts") is None, "куска нет - и выдумывать его нечем"
    assert _handler(feed)._read("index.m3u8") == b"#EXTM3U\n", "манифест берётся не с диска"
