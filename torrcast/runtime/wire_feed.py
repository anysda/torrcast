"""Проводка ленты показа: единственное место, где её слоты видят свой медиатракт."""

from __future__ import annotations

import time

from torrcast.adapters.filesystem.remove_tree import remove_tree
from torrcast.adapters.recode.recode_dir import RECODE_DIR
from torrcast.adapters.side_thread import side_thread
from torrcast.adapters.stream_pack._segment_files import _paths
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.adapters.stream_pack.settle_start import settle_start
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.usecases.feed_pack.configure import configure


def wire_feed() -> None:
    """Отдать ленте показа её внешний мир: имена кусков, упаковку и уборку на диске.

    🔴 Тем же порядком, что и прогреву: прежде эти имена появлялись в сценарии из
    побочного эффекта импорта совместимого фасада `torrcast.stream`, который вписывал их
    в чужие модули через `globals().update`; с его сносом (TC-682) раздача осталась
    только отсюда.

    Отдельным модулем, а не строкой в общем корне: сам прогон упаковки - адаптер (он
    поднимает ffmpeg, пишет во временный файл и меряет часами), и лента знает его ровно
    договором порта (:class:`torrcast.ports.pack_run.pack_factory.PackFactory`). Кем он будет на
    самом деле, решается здесь и больше нигде.
    """
    configure(
        segment_name,
        segment_slot,
        settle_start,
        ffmpeg_pack_command,
        Packer,
        forget_playing,
        RECODE_DIR,
        remove_tree,
        _paths,
        time,
        side_thread,
    )
