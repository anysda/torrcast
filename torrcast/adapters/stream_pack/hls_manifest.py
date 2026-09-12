"""Манифест VOD на весь фильм: длины всех сегментов сетки и ``ENDLIST``.

Собирает его сетка (:meth:`torrcast.adapters.stream_pack.grid.Grid.manifest`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence


def hls_manifest(
    spans: Sequence[float],
    target: int,
    on_keys: bool,
    container: SegmentContainer = MPEGTS,
    *,
    gaps: Collection[int] = (),
) -> str:
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

    ``gaps`` - места, которых в показе не будет: упаковка идёт только вперёд от захода, и
    ниже него живой кусок не появится. Такое место остаётся в ленте со своим ``EXTINF``,
    но объявляется отсутствующим, и приёмник за ним не идёт вовсе. Обещать его нельзя:
    запрос висит выдержку (:attr:`Feed.wait`) и кончается 404, после которого ресивер не
    берёт LOAD минутами.

    🔴 Срезать голову плейлиста вместо этого нельзя: таймлайн приёмника считается ПО
    ПЛЕЙЛИСТУ. Замер на стенде («Интерстеллар», заход 3600 с, слот 335): со срезанной
    головой приёмник доложил ``duration`` 6556.26 вместо 10143.97 и позицию 0.00 вместо
    3600 - то есть ноль показа уехал бы на место захода, а с ним и каждая секунда, которую
    приёмник называет наружу (закладка, доклад вкладки, сверка с ТВ). С дырами тот же
    заход: ``PLAYING`` на 3600.28, ``duration`` 10143.97, и ни одного запроса ниже захода.
    """
    holes = frozenset(gaps)
    lines = [
        "#EXTM3U",
        # Объявить место отсутствующим разрешено с восьмой версии. Без дыр версия остаётся
        # прежней знак в знак: поднимать её там, где нечего объявлять, незачем.
        f"#EXT-X-VERSION:{8 if holes else (7 if container == FMP4 else 3)}",
        f"#EXT-X-TARGETDURATION:{target}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    if on_keys:
        # Не украшение: каждый сегмент начинается с опорного кадра, и приёмнику
        # разрешено начать показ с любого - на этом и держится перемотка.
        lines.append("#EXT-X-INDEPENDENT-SEGMENTS")
    if container == FMP4:
        lines.append('#EXT-X-MAP:URI="init.mp4"')
    for slot, span in enumerate(spans):
        if slot in holes:
            lines.append("#EXT-X-GAP")
        lines += [f"#EXTINF:{span:.6f},", segment_name(slot, container)]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"
