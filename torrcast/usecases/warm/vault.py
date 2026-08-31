"""Каталог прогретого одного показа и бюджет диска на всех.

Читают его показ (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`) и сам прогрев.
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import torrcast.usecases.warm._state as _state
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.segment_container import FMP4, MPEGTS, SegmentContainer
from torrcast.domain.warm_settings import WARM_BUDGET
from torrcast.usecases.warm._vault_disk import (
    _dirs,
    _disk_free,
    _size,
    _title,
    _touched,
    _weigh,
)
from torrcast.usecases.warm.reject import reject as _reject
from torrcast.usecases.warm.relay import relay as _relay
from torrcast.usecases.warm.served_spots import ServedSpots
from torrcast.usecases.warm.settings import FREE_FLOOR, META, SPOT_LAY


@dataclass(slots=True)
class Vault:
    """Каталог прогретого одного показа и бюджет диска на всех.

    Читается отсюда напрямую: показ отдаёт приёмнику файл из этого каталога, не копируя
    его в tmpfs (:meth:`torrcast.usecases.feed_pack.feed.Feed.segment`). Копия стоила бы памяти
    ровно там, где её и не хватает. Метки точечного перекода для раздачи снимаются с
    диска один раз и дальше пополняются через :meth:`ServedSpots.mark`.
    """

    root: Path
    key: str
    budget: int = WARM_BUDGET
    #: Сколько байт раздела не трогаем ни при каких обстоятельствах (:data:`FREE_FLOOR`).
    floor: int = FREE_FLOOR
    title: str = ""
    #: Каким способом ЭТОТ прогрев кладёт точечные куски (:data:`SPOT_LAY`). Пишется в
    #: паспорт и сверяется при заводе каталога (:meth:`relay`).
    lay: str = SPOT_LAY
    #: Чужие ключи, которые бюджет вытеснять не имеет права: серия, которую смотрят
    #: прямо сейчас, для прогрева следующей - чужой каталог (:meth:`fit`). Без этого
    #: прогрев следующей серии выедал бы текущую и обрыв связи убивал бы показ ровно
    #: там, где его и должно было спасти прогретое.
    keep: frozenset[str] = frozenset()
    container: SegmentContainer = MPEGTS
    #: Чем меряется свободное место на разделе. Полем, а не именем внутри :meth:`free`:
    #: правило отказа (:meth:`fit`) обязано быть проверяемым на любом разделе, а не
    #: только на том, который случайно оказался под тестом.
    free_of: Callable[[Path], int] = field(default=_disk_free)
    served: ServedSpots = field(init=False, repr=False)

    def __post_init__(self) -> None:
        self.served = ServedSpots(self.dir)

    @property
    def dir(self) -> Path:
        return self.root / self.key

    def path(self, slot: int) -> Path:
        if self.container == FMP4:
            return self.dir / f"v{slot}.m4s"
        return self.dir / _state.segment_name(slot)

    def have(self, slot: int) -> bool:
        return self.path(slot).exists()

    def head(self) -> Path:
        """Общий заголовок показа (``EXT-X-MAP``): прогрев пакует тем же муксером, и
        заголовок оказывается тут сам собой. Спрашивает его показ, когда живая упаковка
        не поднимется вовсе (:func:`torrcast.usecases.feed_pack.feed_head._head`). Под ``v*``
        имя не подходит, поэтому куском его не считает ни :meth:`slots`, ни показ."""
        return self.dir / "init.mp4"

    def spot(self, slot: int) -> Path:
        """Метка «этот кусок уже перекодирован точечно», а не скопирован.

        Отдельный пустой файл рядом с куском, а не поле в паспорте: прогрев переживает
        снятие показа на любом месте, и после перезапуска надо знать поштучно, что уже
        сделано. Имя не подходит под ``v*.ts``, поэтому ни :meth:`slots`, ни вес каталога
        его не видят.
        """
        return self.dir / f"v{slot}.rec"

    def slots(self, cap: int = 0) -> set[int]:
        """Что уже прогрето. Читается глобом: другого источника правды тут нет и не надо.

        ``cap`` - потолок веса куска у приёмника: тогда считаются только те куски, которые
        показ и правда возьмёт с диска (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`). Ноль -
        всё, что лежит: прогреву решать, куда идти дальше, надо по файлам (:meth:`Warmer._missing`),
        иначе тяжёлое место перекладывалось бы вечно.
        """
        found: set[int] = set()
        with contextlib.suppress(OSError):
            for path in self.dir.glob("v*.m4s" if self.container == FMP4 else "v*.ts"):
                slot = _state.segment_slot(path.name)
                if slot < 0 or (cap > 0 and _size(path) > cap):
                    continue
                found.add(slot)
        return found

    def open(self) -> None:
        """Завести каталог и паспорт. Паспорт нужен бюджету и способу выкладки: по его
        времени изменения считается давность показа (:meth:`fit`), а по записанному в нём
        способу - надо ли перекладывать точечные куски (:meth:`relay`)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.touch()

    def relay(self) -> tuple[int, ...]:
        return _relay(self)

    def reject(self, slot: int) -> None:
        _reject(self, slot)

    def touch(self) -> None:
        at = _state._environment.epoch()
        card = {"key": self.key, "title": self.title, "at": at, "lay": self.lay}
        with contextlib.suppress(OSError):
            (self.dir / META).write_text(json.dumps(card), encoding="utf-8")

    def size(self) -> int:
        return _weigh(self.dir)

    def clear(self) -> None:
        """Показ досмотрен (или брошен насовсем) — прогретое стирается целиком."""
        _state._environment.remove_tree(self.dir)

    def free(self) -> int:
        """Сколько байт свободно на разделе прогрева."""
        return self.free_of(self.root)

    def fit(self, need: int) -> str:
        """Место под ещё ``need`` байт: пусто — нашлось, иначе честная причина отказа.

        Бюджет один на всё прогретое, а не на показ: два фильма подряд не должны
        сложиться в сорок гигабайт. Вытесняются **чужие** каталоги, начиная с самого
        давнего, - свой не трогаем никогда, иначе прогрев съедал бы сам себя. Не свой,
        но и не чужой - :attr:`keep`: соседняя серия того же показа.

        Причин отказа две, и путать их нельзя: наш бюджет и чужое место на разделе.
        Рядом живут и состояние, и раздача, и система — упереть раздел в ноль прогревом
        не имеет права ни один бюджет.
        """
        mine = {self.key, *self.keep}
        others = sorted(
            (path for path in _dirs(self.root) if path.name not in mine),
            key=_touched,
        )
        while others and _weigh(self.root) + need > self.budget:
            gone = others.pop(0)
            # Вес и имя снимаем ДО сноса: после ``rmtree`` сказать, что именно и на сколько
            # освободили, уже не по чему, а в ленте это и есть вся ценность записи.
            _state._environment.emit(
                "evict", key=gone.name, freed=_weigh(gone), need=int(need), title=_title(gone)
            )
            _state._environment.remove_tree(gone)
        if need > self.budget - _weigh(self.root):
            return phrase("warm.budget_exhausted", budget=f"{self.budget / 1e9:.0f}")
        if need + self.floor > self.free():
            return phrase("warm.floor_reached", free=f"{self.free() / 1e9:.1f}")
        return ""
