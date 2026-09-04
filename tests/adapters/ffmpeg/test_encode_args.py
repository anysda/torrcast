"""Проверяет аргументы x264 без запуска ffmpeg."""

from torrcast.adapters.ffmpeg.encode_args import encode_args


def test_builds_rate_keys_filters_and_hdr_marks() -> None:
    arguments = encode_args(
        preset="ultrafast",
        mbit=9.0,
        maxrate=9.72,
        bufsize=4.86,
        keyframes=[0.98, 10.0],
        filters="scale=-2:1080",
        hdr=True,
    )
    assert arguments[:2] == ["-vf", "scale=-2:1080"]
    assert "-level" not in arguments, "уровень в потоке пишет x264, а не мы"
    assert "0.980,10.000" in arguments
    assert arguments[-6:] == [
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
    ]
