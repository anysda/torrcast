"""Raster dimensions used to rejudge poster files written before the current shelf rule."""

from __future__ import annotations

import struct

from hass.picture_size import picture_size


def test_png_and_gif_dimensions_are_read_from_their_headers() -> None:
    png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + struct.pack(">II", 500, 750)
    gif = b"GIF89a" + struct.pack("<HH", 640, 480)

    assert picture_size(png) == (500, 750)
    assert picture_size(gif) == (640, 480)


def test_jpeg_dimensions_are_read_from_its_start_of_frame() -> None:
    jpeg = (
        b"\xff\xd8\xff\xe0\x00\x02\xff\xc0\x00\x0b\x08"
        + struct.pack(">HH", 750, 500)
        + b"\x03\x01\x11\x00"
    )

    assert picture_size(jpeg) == (500, 750)


def test_each_webp_header_yields_its_dimensions() -> None:
    extended = (
        b"RIFF\x00\x00\x00\x00WEBPVP8X"
        + b"\x00" * 8
        + (499).to_bytes(3, "little")
        + (749).to_bytes(3, "little")
    )
    lossy = (
        b"RIFF\x00\x00\x00\x00WEBPVP8 "
        + b"\x00" * 7
        + b"\x9d\x01\x2a"
        + struct.pack("<HH", 500, 750)
    )
    bits = (499) | (749 << 14)
    lossless = (
        b"RIFF\x00\x00\x00\x00WEBPVP8L"
        + b"\x00" * 4
        + b"/"
        + bits.to_bytes(4, "little")
        + b"\x00" * 5
    )

    assert picture_size(extended) == (500, 750)
    assert picture_size(lossy) == (500, 750)
    assert picture_size(lossless) == (500, 750)


def test_unknown_or_truncated_bytes_have_no_dimensions() -> None:
    assert picture_size(b"") is None
    assert picture_size(b"\xff\xd8\xff") is None


__all__: list[str] = []
