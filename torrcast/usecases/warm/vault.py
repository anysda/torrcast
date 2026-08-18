"""Каталог прогретого одного показа и бюджет диска на всех.

Читают его показ (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`) и сам прогрев.
"""

from __future__ import annotations

import contextlib
import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import torrcast.usecases.warm._state as _state
from torrcast.domain.warm_settings import WARM_BUDGET
from torrcast.usecases.warm.settings import FREE_FLOOR, META


def _disk_free(root: Path) -> int:
    """Сколько байт свободно на разделе, где лежит корень прогретого; беда - ноль."""
    try:
        stat = os.statvfs(root)
    except OSError:
        return 0
    return stat.f_bavail * stat.f_frsize


@dataclass(slots=True)
class Vault:
    """Каталог прогретого одного показа и бюджет диска на всех.

    Читается отсюда напрямую: показ отдаёт приёмнику файл из этого каталога, не копируя
    его в tmpfs (:meth:`torrcast.usecases.feed_pack.feed.Feed.segment`). Копия стоила бы памяти ровно
    там, где её и не хватает.
    """

    root: Path
    key: str
    budget: int = WARM_BUDGET
    #: Сколько байт раздела не трогаем ни при каких обстоятельствах (:data:`FREE_FLOOR`).
    floor: int = FREE_FLOOR
    title: str = ""
    #: Чужие ключи, которые бюджет вытеснять не имеет права: серия, которую смотрят
    #: прямо сейчас, для прогрева следующей - чужой каталог (:meth:`fit`). Без этого
    #: прогрев следующей серии выедал бы текущую и обрыв связи убивал бы показ ровно
    #: там, где его и должно было спасти прогретое.
    keep: frozenset[str] = frozenset()
    #: Чем меряется свободное место на разделе. Полем, а не именем внутри :meth:`free`:
    #: правило отказа (:meth:`fit`) обязано быть проверяемым на любом разделе, а не
    #: только на том, который случайно оказался под тестом.
    free_of: Callable[[Path], int] = field(default=_disk_free)

    @property
    def dir(self) -> Path:
        return self.root / self.key

    def path(self, slot: int) -> Path:
        return self.dir / _state.segment_name(slot)

    def have(self, slot: int) -> bool:
        return self.path(slot).exists()

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
            for path in self.dir.glob("v*.ts"):
                slot = _state.segment_slot(path.name)
                if slot < 0 or (cap > 0 and _size(path) > cap):
                    continue
                found.add(slot)
        return found

    def open(self) -> None:
        """Завести каталог и паспорт. Паспорт нужен ровно бюджету: по его времени
        изменения считается давность показа (:meth:`fit`)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.touch()

    def touch(self) -> None:
        with contextlib.suppress(OSError):
            (self.dir / META).write_text(
                json.dumps(
                    {"key": self.key, "title": self.title, "at": _state._environment.epoch()}
                ),
                encoding="utf-8",
            )

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
            return f"бюджет диска {self.budget / 1e9:.0f} ГБ исчерпан"
        if need + self.floor > self.free():
            return f"на разделе свободно {self.free() / 1e9:.1f} ГБ - это последний запас"
        return ""


def _dirs(root: Path) -> list[Path]:
    try:
        return [path for path in root.iterdir() if path.is_dir()]
    except OSError:
        return []


def _touched(path: Path) -> float:
    try:
        return (path / META).stat().st_mtime
    except OSError:
        return 0.0


def _title(path: Path) -> str:
    """Название вытесняемого показа из его паспорта; нет паспорта - пустая строка."""
    with contextlib.suppress(OSError, ValueError):
        found = json.loads((path / META).read_text(encoding="utf-8"))
        if isinstance(found, dict):
            return str(found.get("title", ""))
    return ""


def _size(path: Path) -> int:
    """Вес файла; не прочли - ноль. Ноль тут безопасен: кусок, пропавший между глобом и
    ``stat``, отдача уже переживает (404 → приёмник просит снова)."""
    try:
        return path.stat().st_size
    except OSError:
        return 0


def _weigh(where: Path) -> int:
    total = 0
    with contextlib.suppress(OSError):
        for path in where.rglob("v*.ts"):
            with contextlib.suppress(OSError):
                total += path.stat().st_size
    return total
