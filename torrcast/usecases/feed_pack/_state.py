"""Внешний мир ленты под прежними именами: медиатракт, часы, диск и подпроцессы.

Слоты медиатракта заполняет :func:`torrcast.usecases.feed_pack.configure.configure`,
читают их модули пакета - и читают в момент работы, а не на импорте.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from torrcast.ports.feed_grid import FeedGrid

#: Сетка сегментов в том объёме, в каком её знают упаковщик и лента.
Grid = FeedGrid

#: Имя файла сегмента по месту в фильме и обратный разбор имени в место.
segment_name: Callable[[int], str]
segment_slot: Callable[[str], int]
#: Куда на самом деле встанет ffmpeg после ``-ss``, и чем паковать по сетке.
pack_start: Callable[..., float]
ffmpeg_pack_command: Callable[..., list[str]]
#: Снять флажок картинки и имя каталога перекодированных кусков.
forget_playing: Callable[[Path], None]
RECODE_DIR: str

# ⚠️ Подпроцессы, временный файл, дерево каталогов и часы - это внешний мир
# :class:`torrcast.usecases.feed_pack.packer.Packer`, а сам он адаптерный по сути и пока
# живёт в слое сценариев (TC-625). Пока он не переехал, зависимость называется строкой:
# честный ``import subprocess`` в сценарии не сделал бы код правильнее, он лишь
# переписал бы одно нарушение раскладки в другое. Собраны они здесь, в одном месте, а не
# рассыпаны по модулям пакета - чтобы переезд трогал ровно один файл.
shutil = import_module("shutil")
subprocess = import_module("subprocess")
tempfile = import_module("tempfile")
clock_port = import_module("time")
time = clock_port
