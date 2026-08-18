"""Зеркало решения о СПЛОШНОМ перекоде: белый список кодеков, глубина, кадр и вес."""

from __future__ import annotations

from torrcast.domain.config import Config
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.playback._encode_all import _encode_all


def test_a_codec_the_receiver_decodes_goes_by_copy() -> None:
    """H.264 8 бит приёмник декодирует - перекодировать нечего."""
    assert _encode_all(Config(recode=True), "h264", 5.0, 8, CAUTIOUS) is None


def test_a_codec_outside_the_white_list_goes_by_whole_recode() -> None:
    """Кодека нет в белом списке - файл едет сплошным перекодом, а не копией."""
    assert _encode_all(Config(recode=True), "av1", 5.0, 8, CAUTIOUS) is not None


def test_ten_bits_are_asked_alongside_the_codec() -> None:
    """Hi10P зовётся тем же ``h264``, а приёмник его не берёт - решает глубина."""
    assert _encode_all(Config(recode=True), "h264", 5.0, 10, CAUTIOUS) is not None


def test_a_heavy_file_goes_by_whole_recode_even_in_a_known_codec() -> None:
    """Выше жёсткого потолка тяжёл КАЖДЫЙ кусок - посегментный перекод тут вырождается."""
    config = Config(recode=True, bitrate_hard_mbit=25.0)

    assert _encode_all(config, "h264", 37.0, 8, CAUTIOUS) is not None


def test_recoding_switched_off_means_no_recoding_at_all() -> None:
    """Перекод выключен настройкой - решения нет, что бы ни лежало во входе."""
    assert _encode_all(Config(recode=False), "av1", 40.0, 10, CAUTIOUS, frame=2160) is None


def test_a_frame_above_the_ceiling_is_squeezed_and_not_refused() -> None:
    """2160p приёмник не берёт вовсе - и это не отказ, а перекод со скейлом вниз."""
    made = _encode_all(Config(recode=True), "h264", 20.0, 8, CAUTIOUS, frame=2160)

    assert made is not None and made.out_frame == CAUTIOUS.recode_frame
