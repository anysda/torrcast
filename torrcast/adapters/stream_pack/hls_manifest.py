"""Манифест VOD на весь фильм: длины всех сегментов сетки и ``ENDLIST``.

Собирает его сетка (:meth:`torrcast.adapters.stream_pack.grid.Grid.manifest`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_probe import segment_name

if TYPE_CHECKING:
    from collections.abc import Sequence


def hls_manifest(spans: Sequence[float], target: int, on_keys: bool) -> str:
    """Манифест VOD на **весь фильм**: все сегменты сетки и ``ENDLIST``.

    Приёмнику неоткуда узнать длительность, кроме
    манифеста: у скользящего live-плейлиста её нет вовсе, поэтому ТВ считал показ
    эфиром и не давал ни таймлайна, ни перемотки. Здесь длительность — сумма
    ``EXTINF``, то есть ровно длина фильма, и перемотка разрешена в любую его точку.

    Манифест **статический**: он не зависит от того, что упаковано прямо сейчас, и
    перечисляет сегменты, которых на диске ещё нет. Целый фильм в tmpfs не влезает —
    но приёмнику и не нужен файл раньше, чем он его попросит: за это отвечает
    :class:`Feed`, которая на запрос неупакованного места пакует оттуда.

    Проверено на живом Q70D: ``duration`` в MEDIA_STATUS = длине манифеста,
    ``seek`` в произвольную точку отрабатывает за доли секунды и показ продолжается.
    """
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    if on_keys:
        # Не украшение: каждый сегмент начинается с опорного кадра, и приёмнику
        # разрешено начать показ с любого - на этом и держится перемотка.
        lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    for slot, span in enumerate(spans):
        lines += [f"#EXTINF:{span:.6f},", segment_name(slot)]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"
