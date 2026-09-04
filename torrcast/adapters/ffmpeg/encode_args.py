"""Собирает аргументы видеокодера x264; их вызывает модель перекода."""

from collections.abc import Iterable


def encode_args(
    *,
    preset: str,
    mbit: float,
    maxrate: float,
    bufsize: float,
    keyframes: Iterable[float],
    filters: str = "",
    hdr: bool = False,
) -> list[str]:
    """Собрать прежние параметры x264 и преобразования цвета.

    Уровень тут НЕ задаётся вовсе: его пишет сам x264 по потоку, который получился
    (:meth:`torrcast.adapters.recode.encode.Encode.args`).
    """
    keys = ",".join(f"{point:.3f}" for point in keyframes)
    video = [
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-b:v",
        f"{mbit:.2f}M",
        "-maxrate",
        f"{maxrate:.2f}M",
        "-bufsize",
        f"{bufsize:.2f}M",
        "-pix_fmt",
        "yuv420p",
        "-sc_threshold",
        "0",
        "-force_key_frames",
        keys,
    ]
    if filters:
        video = ["-vf", filters, *video]
    if hdr:
        video += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    return video
