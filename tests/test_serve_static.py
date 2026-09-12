"""Раздача самой страницы и её файлов."""

from __future__ import annotations

import json
import re
import struct
import zlib
from pathlib import Path

import pytest

from web.request import Request
from web.serve_static import STATIC, serve_static

ROOT = Path(__file__).resolve().parents[1]
HA_ICON = ROOT / "custom_components/torrcast/brand/icon.png"


def _ask(path: str) -> tuple[int, bytes, str]:
    answer = serve_static(Request("GET", path, {}, {}))
    return answer.code, answer.body, answer.kind


def test_the_root_path_gives_the_page_itself() -> None:
    code, body, kind = _ask("/")

    assert code == 200
    assert kind == "text/html; charset=utf-8"
    assert b"tc-root" in body


def test_every_kind_the_page_needs_is_signed_by_its_own_type() -> None:
    signed = {
        "/static/style.css": "text/css; charset=utf-8",
        "/static/app.js": "text/javascript; charset=utf-8",
        "/static/hls-1.5.17.min.js": "text/javascript; charset=utf-8",
        "/static/fonts/archivo-latin.woff2": "font/woff2",
        "/static/favicon.png": "image/png",
    }

    assert {path: _ask(path)[2] for path in signed} == signed


def test_the_vendored_player_arrives_whole() -> None:
    code, body, _kind = _ask("/static/hls-1.5.17.min.js")

    assert code == 200
    assert len(body) == (STATIC / "hls-1.5.17.min.js").stat().st_size


def test_the_page_declares_its_favicon() -> None:
    page = (STATIC / "index.html").read_bytes()

    assert b'<link rel="icon" type="image/png" href="/static/favicon.png">' in page


def test_the_favicon_keeps_the_ha_shape_in_the_web_acid_colour() -> None:
    code, body, kind = _ask("/static/favicon.png")

    assert code == 200
    assert kind == "image/png"
    assert body
    assert tuple(pixel[3] for pixel in _pixels(body)) == tuple(
        pixel[3] for pixel in _pixels(HA_ICON.read_bytes())
    )
    assert {pixel[:3] for pixel in _pixels(body) if pixel[3]} == {_acid_colour()}


def _acid_colour() -> bytes:
    found = re.search(r"--tc-acid:\s*(#[0-9A-F]{6});", (STATIC / "style.css").read_text())
    assert found is not None
    return bytes.fromhex(found.group(1)[1:])


def _pixels(png: bytes) -> tuple[bytes, ...]:
    """Read the RGBA scanlines of our 8-bit, non-interlaced PNG without a dependency."""
    width, height, depth, colour, _compression, _filter, interlace = struct.unpack(
        ">IIBBBBB", png[16:29]
    )
    assert (depth, colour, interlace) == (8, 6, 0)
    packed = _idat(png)
    rows = _unfilter(zlib.decompress(packed), width, height)
    return tuple(rows[offset : offset + 4] for offset in range(0, len(rows), 4))


def _idat(png: bytes) -> bytes:
    place = 8
    parts = []
    while place < len(png):
        length = struct.unpack(">I", png[place : place + 4])[0]
        kind = png[place + 4 : place + 8]
        if kind == b"IDAT":
            parts.append(png[place + 8 : place + 8 + length])
        place += length + 12
    return b"".join(parts)


def _unfilter(packed: bytes, width: int, height: int) -> bytes:
    stride = width * 4
    previous = bytearray(stride)
    rows = bytearray()
    place = 0
    for _ in range(height):
        filter_kind = packed[place]
        filtered = packed[place + 1 : place + stride + 1]
        current = bytearray(stride)
        for column, value in enumerate(filtered):
            left = current[column - 4] if column >= 4 else 0
            above = previous[column]
            upper_left = previous[column - 4] if column >= 4 else 0
            current[column] = (value + _filter_value(filter_kind, left, above, upper_left)) % 256
        rows.extend(current)
        previous = current
        place += stride + 1
    return bytes(rows)


def _filter_value(kind: int, left: int, above: int, upper_left: int) -> int:
    if kind == 0:
        return 0
    if kind == 1:
        return left
    if kind == 2:
        return above
    if kind == 3:
        return (left + above) // 2
    assert kind == 4
    probe = left + above - upper_left
    distances = abs(probe - left), abs(probe - above), abs(probe - upper_left)
    return (left, above, upper_left)[distances.index(min(distances))]


def test_a_walk_up_does_not_escape_the_page() -> None:
    """Выход наружу отвечает 404 и НЕ отдаёт байтов: проверяется и то, и другое."""
    for path in (
        "/static/../pyproject.toml",
        "/static/../../etc/passwd",
        "/static/fonts/../../pyproject.toml",
        "/static//etc/passwd",
    ):
        code, body, _kind = _ask(path)
        assert code == 404, path
        assert json.loads(body) == {"error": "not_found"}, path


def test_a_link_pointing_out_of_the_page_is_the_same_walk_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "secret.css"
    outside.write_text("body{}", encoding="utf-8")
    home = tmp_path / "static"
    home.mkdir()
    (home / "link.css").symlink_to(outside)
    monkeypatch.setattr("web.serve_static.STATIC", home)

    assert _ask("/static/link.css")[0] == 404


def test_a_file_edited_between_two_calls_arrives_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Кэша у страницы нет: правка обязана доехать следующим же запросом."""
    home = tmp_path / "static"
    home.mkdir()
    (home / "style.css").write_text("body{color:red}", encoding="utf-8")
    monkeypatch.setattr("web.serve_static.STATIC", home)
    before = _ask("/static/style.css")

    (home / "style.css").write_text("body{color:lime}", encoding="utf-8")
    after = _ask("/static/style.css")

    assert before[1] == b"body{color:red}"
    assert after[1] == b"body{color:lime}"


def test_the_page_is_never_kept_in_a_cache() -> None:
    answer = serve_static(Request("GET", "/static/style.css", {}, {}))

    assert dict(answer.headers())["Cache-Control"] == "no-store"


def test_a_name_that_is_not_a_file_is_a_stranger() -> None:
    assert _ask("/static/")[0] == 404
    assert _ask("/static/fonts")[0] == 404
    assert _ask("/static/nothing-like-this.css")[0] == 404
