"""Проверки названия видеокодека."""

from torrcast.domain.codec_name import codec_name


def test_depth_is_named() -> None:
    assert codec_name("h264", 10) == "h264 10 бит"
