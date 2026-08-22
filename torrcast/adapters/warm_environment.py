"""Системная среда сценария прогрева."""

import shutil
import time
from collections.abc import Callable
from pathlib import Path

from torrcast.adapters.filesystem.trace_journal import evict, skew, warmth
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.pack_start import pack_start as _pack_start
from torrcast.adapters.stream_pack.packer import Packer
from torrcast.adapters.stream_pack.spot_out import spot_out
from torrcast.adapters.stream_probe.segment_name import segment_name as _segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot as _segment_slot
from torrcast.domain._hms import _hms
from torrcast.ports.journal.slot import journal
from torrcast.ports.json_value import JsonValue
from torrcast.ports.warm_environment.warm_packer import WarmPacker

#: Схемы событий ленты, которые ставит прогрев: имя события приходит с места вызова
#: (:mod:`torrcast.usecases.warm`), а дом схемы назван здесь модулем, а не пакетом.
_SCHEMAS: dict[str, Callable[..., None]] = {
    "evict": evict.evict,
    "skew": skew.skew,
    "warmth": warmth.warmth,
}

#: Слот сборки команды: имена параметров тут не повторяются нарочно - полный договор
#: стоит в порту, а слот держит адрес, по которому его ставит подмена медиатракта.
_pack_command: Callable[..., list[str]] = ffmpeg_pack_command
#: Слот выкладки точечного перекода: под ним поднимаются ffmpeg и ffprobe, и зеркала
#: прогрева подменяют его ровно здесь.
_spot_out: Callable[..., bool] = spot_out


# ⚠️ Медиатракт зовётся ЧЕРЕЗ модульные слоты выше, а не связывается на сборке класса
# (``pack_start = staticmethod(...)``): подмена медиатракта в зеркалах прогрева ставится
# ровно сюда, и связывание на сборке обесточило бы её молча (TC-666).


class _SystemWarmEnvironment:
    """Связывает порт прогрева с часами, диском и телеметрией."""

    epoch = staticmethod(time.time)
    monotonic = staticmethod(time.monotonic)
    sleep = staticmethod(time.sleep)

    @staticmethod
    def segment_name(slot: int) -> str:
        return _segment_name(slot)

    @staticmethod
    def segment_slot(name: str) -> int:
        return _segment_slot(name)

    @staticmethod
    def hms(seconds: float) -> str:
        # ⚠️ Похожая :func:`torrcast.domain.digest._words._hms` тут НЕ подходит: она опускает
        # часы у коротких отрезков, а прогрев печатает их всегда.
        return _hms(seconds)

    @property
    def packer_type(self) -> WarmPacker:
        return Packer

    @staticmethod
    def pack_command(*args: object, **kwargs: object) -> list[str]:
        return _pack_command(*args, **kwargs)

    @staticmethod
    def pack_start(source_url: str, at: float) -> float:
        return _pack_start(source_url, at)

    @staticmethod
    def spot_out(*args: object, **kwargs: object) -> bool:
        return _spot_out(*args, **kwargs)

    audio_mbit = 0.192
    ts_overhead = 1.03

    @staticmethod
    def remove_tree(path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def emit(event: str, *args: object, **facts: object) -> None:
        # Схема события - файл в пакете ленты, и дом каждой названа тут по имени файла.
        # Раньше на этом месте стоял ``getattr`` по пакету: имя события приходит с места
        # вызова, и пакет раздавал схемы своим namespace. Теперь пакет имён не раздаёт,
        # а зовущий берёт схему из её модуля.
        _SCHEMAS[event](*args, **facts)

    @staticmethod
    def mark(name: str, **facts: JsonValue) -> None:
        journal().mark(name, **facts)


environment = _SystemWarmEnvironment()
