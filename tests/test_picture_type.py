"""Зеркало :mod:`hass.picture_type`: тип картинки читается подписью, а не адресом."""

from __future__ import annotations

from hass.picture_type import UNKNOWN_TYPE, picture_type


def test_the_formats_are_told_apart_by_their_first_bytes() -> None:
    assert picture_type(b"\x89PNG\r\n\x1a\n\x00\x00") == "image/png"
    assert picture_type(b"\xff\xd8\xff\xe0\x00\x10JFIF") == "image/jpeg"
    assert picture_type(b"GIF89a") == "image/gif"
    assert picture_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"


def test_a_vector_name_does_not_make_the_body_a_vector() -> None:
    """🔴 Уменьшенная копия ``.svg`` приезжает от Wikimedia растром PNG.

    Читай тип по расширению адреса - и карточке уехал бы ``image/svg+xml`` на PNG-байтах.
    """
    thumb = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
    assert picture_type(thumb) == "image/png"


def test_an_unknown_signature_is_named_a_stream_of_bytes_and_not_a_silence() -> None:
    assert picture_type(b"<svg xmlns=") == UNKNOWN_TYPE
    assert picture_type(b"") == UNKNOWN_TYPE
