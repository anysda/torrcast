"""Системная среда сценария прогрева."""

import shutil
import time
from collections.abc import Callable
from importlib import import_module
from pathlib import Path

from torrcast.adapters.filesystem import trace_journal
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.pack_start import pack_start as _pack_start
from torrcast.adapters.stream_probe.segment_name import segment_name as _segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot as _segment_slot
from torrcast.ports.journal import journal
from torrcast.ports.json_value import JsonValue
from torrcast.ports.warm_environment import WarmPack, WarmPacker

#: Слот сборки команды: имена параметров тут не повторяются нарочно - полный договор
#: стоит в порту, а слот держит адрес, по которому его ставит подмена медиатракта.
_pack_command: Callable[..., list[str]] = ffmpeg_pack_command


# ⚠️ Медиатракт зовётся ЧЕРЕЗ модульные слоты выше, а не связывается на сборке класса
# (``pack_start = staticmethod(...)``): подмена медиатракта в зеркалах прогрева ставится
# ровно сюда, и связывание на сборке обесточило бы её молча (TC-666).


class _LazyPacker:
    """Откладывает импорт упаковщика до настоящего запуска прогрева.

    ⚠️ Имя упаковщика тут строкой не по лени: :class:`Packer` объявлен в слое сценариев
    (:mod:`torrcast.usecases.feed_pack`), а адаптеру импортировать сценарий запрещает
    правило слоёв. Пока упаковщик не переедет в адаптеры, честного имени у него здесь
    нет: прямой импорт разменял бы одно нарушение гейта на другое, покрупнее.
    """

    @classmethod
    def start(cls, *args: object, **kwargs: object) -> WarmPack:
        packer = import_module("torrcast.usecases.feed_pack.packer").Packer
        started: WarmPack = packer.start(*args, **kwargs)
        return started


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
        # ⚠️ Как и упаковщик выше, «ч:мм:сс» живёт в слое сценариев
        # (:mod:`torrcast.usecases.rank`) и адаптеру по имени недоступен. Похожая
        # :func:`torrcast.domain.digest._hms` НЕ подходит: она опускает часы у коротких
        # отрезков, а прогрев печатает их всегда.
        #
        # 🔴 Строка тут раньше называла плоский namespace прежнего монолита
        # (``torrcast.cli``), а не дом самой единицы: со сносом namespace прогрев уходил
        # в `AttributeError` внутри фоновой нитки цепочки серий - молча и посреди показа.
        # Строка обязана называть настоящий дом, даже пока она строка.
        text: str = import_module("torrcast.usecases.rank")._hms(seconds)
        return text

    @property
    def packer_type(self) -> WarmPacker:
        return _LazyPacker

    @staticmethod
    def pack_command(*args: object, **kwargs: object) -> list[str]:
        return _pack_command(*args, **kwargs)

    @staticmethod
    def pack_start(source_url: str, at: float) -> float:
        return _pack_start(source_url, at)

    audio_mbit = 0.192
    max_segment_bytes = 16_000_000
    ts_overhead = 1.03

    @staticmethod
    def remove_tree(path: Path) -> None:
        shutil.rmtree(path, ignore_errors=True)

    @staticmethod
    def emit(event: str, *args: object, **facts: object) -> None:
        # Схема события - файл в пакете ленты; имя события приходит с места вызова,
        # но сам пакет назван импортом и виден графу зависимостей.
        getattr(trace_journal, event)(*args, **facts)

    @staticmethod
    def mark(name: str, **facts: JsonValue) -> None:
        journal().mark(name, **facts)


environment = _SystemWarmEnvironment()
