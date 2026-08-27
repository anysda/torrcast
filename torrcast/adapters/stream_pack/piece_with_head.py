"""Чем открыть кусок CMAF: голым он не открывается, а вместе со своим заголовком - да.

Спрашивают это склейка (:func:`torrcast.adapters.stream_pack.merge_tracks.merge_tracks`) и
выкладка, когда меряет, где на ленте стоят дорожки куска
(:mod:`torrcast.adapters.stream_pack.packer_publish`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def piece_with_head(chunk: Path, head: Path | None) -> str:
    """Имя куска для ffmpeg: с заголовком впереди, если он есть, и как есть, если нет.

    🔴 Кусок CMAF - это ``moof mdat`` без единого описания дорожек, и ffmpeg на нём честно
    сдаётся: ``trun track id unknown, no tfhd was found``, код возврата 183. Ровно поэтому
    склейка ужатого места не выходила на этом контейнере НИ РАЗУ - 196 отказов против 26
    удачных на mpegts, - и дело было не в муксере, а во входе.

    Читается кусок вместе с заголовком через ``concat:``: это протокол чтения, лишнего
    файла он не создаёт и в tmpfs ничего не кладёт. Замер: выход байт в байт тот же, что
    через временные склеенные копии.
    """
    if head is None or not head.exists():
        return str(chunk)
    return f"concat:{head}|{chunk}"
