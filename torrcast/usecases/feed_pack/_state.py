"""Внешний мир ленты под прежними именами: медиатракт, часы и уборка на диске.

Слоты медиатракта заполняет :func:`torrcast.usecases.feed_pack.configure.configure`,
читают их модули пакета - и читают в момент работы, а не на импорте.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path

from torrcast.ports.feed_clock import FeedClock
from torrcast.ports.feed_grid import FeedGrid
from torrcast.ports.pack_run.pack_factory import PackFactory

#: Сетка сегментов в том объёме, в каком её знают упаковщик и лента.
Grid = FeedGrid

#: Имя файла сегмента по месту в фильме и обратный разбор имени в место.
segment_name: Callable[[int], str]
segment_slot: Callable[[str], int]
#: Куда на самом деле встанет ffmpeg после ``-ss``, и чем паковать по сетке.
pack_start: Callable[..., float]
ffmpeg_pack_command: Callable[..., list[str]]
#: Чем поднять прогон упаковки. Сам прогон адаптерный - процесс ffmpeg, временный файл
#: и часы, - и живёт он в медиатракте (:mod:`torrcast.adapters.stream_pack.packer`); сюда
#: его кладёт композиция, а договор ему называет порт (:class:`PackFactory`).
Packer: PackFactory
#: Снять флажок картинки и имя каталога перекодированных кусков.
forget_playing: Callable[[Path], None]
RECODE_DIR: str
#: Убрать каталог целиком и перечислить куски сетки, лежащие в каталоге: и то, и другое
#: - работа с диском, и делает её медиатракт, а лента только просит.
remove_tree: Callable[[Path], None]
segment_paths: Callable[[Path], list[Path]]

#: Часы ленты - слот, как и всё остальное здесь; заполняет его та же :func:`configure`.
#:
#: ⚠️ Умолчание тут не для красоты: :class:`torrcast.usecases.feed_pack.feed_state._State`
#: берёт отсюда ``monotonic`` на сборке своего поля, то есть раньше любой композиции, и
#: без готового значения импорт пакета не состоялся бы вовсе.
clock_port: FeedClock = time
