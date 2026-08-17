"""Плейлист со срезанной головой: чем кормить декодер при заходе с середины."""

from __future__ import annotations

import math
from typing import Final

#: Допуск, с которым место захода ложится на сетку манифеста. ``EXTINF`` округлён до
#: шести знаков, и сумма таких длительностей не совпадает с границей сетки бит в бит:
#: 10.023222 + 10 + 10 + 10 + 10 даёт 50.02322200000001, и заход ровно на эту границу
#: съезжал бы на кусок НАЗАД - то есть тащил бы за собой упаковку, ради чего голова
#: плейлиста и срезается.
GRID_SLACK: Final = 0.001


def trimmed_playlist(
    segments: list[tuple[str, float]], base: str, at: float
) -> tuple[str, float] | None:
    """Плейлист с куска, в который целится заход, и остаток ``-ss`` внутрь этого куска.

    🔴 ``ffmpeg -ss`` по адресу плейлиста сперва ОТКРЫВАЕТ вход - забирает самый первый
    сегмент, чтобы опознать дорожки, - и только потом перематывается. Раздача видит
    запрос первого куска и уходит паковать с нуля, поэтому продолжение с середины стоит
    ей лишнего захода упаковки на слот 0. Приёмник головы плейлиста не трогает вовсе:
    LOAD с ``current_time`` спрашивает тот кусок, в который целится, и дальше идёт вперёд.

    Поэтому декодеру достаётся не адрес плейлиста, а плейлист со срезанной головой: те же
    куски начиная с нужного, адресами ``base`` на ту же раздачу. Открывается ffmpeg тем
    самым куском, остаток забирает по сети подряд, как ТВ, а ``-ss`` остаётся ровно
    остатком ВНУТРЬ куска - позиция не разъезжается с запрошенной.

    ``None`` - резать нечего: заход в первый же кусок и так начинается с головы.
    """
    starts: list[float] = []
    clock = 0.0
    for _, seconds in segments:
        starts.append(clock)
        clock += seconds
    first = max((s for s, start in enumerate(starts) if start <= at + GRID_SLACK), default=0)
    if first == 0:
        return None
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{max(1, math.ceil(max(s for _, s in segments)))}",
        f"#EXT-X-MEDIA-SEQUENCE:{first}",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    for name, seconds in segments[first:]:
        lines += [f"#EXTINF:{seconds:.6f},", f"{base}/{name}"]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n", max(0.0, at - starts[first])
