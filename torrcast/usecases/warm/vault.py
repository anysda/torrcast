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
from torrcast.domain.warm_settings import WARM_BUDGET
from torrcast.usecases.warm._vault_disk import (
    _dirs,
    _disk_free,
    _lay,
    _size,
    _spot_marks,
    _title,
    _touched,
    _weigh,
)
from torrcast.usecases.warm.settings import FREE_FLOOR, META, SPOT_LAY


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
    #: Каким способом ЭТОТ прогрев кладёт точечные куски (:data:`SPOT_LAY`). Пишется в
    #: паспорт и сверяется при заводе каталога (:meth:`relay`).
    lay: str = SPOT_LAY
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
        """Завести каталог и паспорт. Паспорт нужен бюджету и способу выкладки: по его
        времени изменения считается давность показа (:meth:`fit`), а по записанному в нём
        способу - надо ли перекладывать точечные куски (:meth:`relay`)."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.touch()

    def relay(self) -> tuple[int, ...]:
        """Убрать куски, положенные ПРЕЖНИМ способом выкладки; вернуть их места.

        Способ выкладки в ключ каталога не входит и входить не должен
        (:func:`torrcast.usecases.warm.warm_key.warm_key`): ключ называет содержимое куска, а на
        детерминированной сетке стоит переиспользование прошлых заходов. Из-за этого каталог,
        прогретый прежним способом, находится по тому же ключу, метки ``v{N}.rec`` считают его
        точечные куски сделанными, и починка выкладки до них не доезжает - старые куски лежат
        под теми же именами и уезжают зрителю.

        Перекладываются ровно помеченные места, а не весь каталог: копию точечная работа не
        трогала, и сброс каталога целиком стоил бы прогрева заново. Кусок стирается вместе с
        меткой - иначе он числился бы сделанным (:func:`torrcast.usecases.warm.missing._missing`,
        :func:`torrcast.usecases.warm._warm_count._spots_left`) и остался бы лежать как есть.

        🔴 Стирается именно ФАЙЛ, а не одна метка. Точечный перекод кладётся поверх копии
        этого же места и берёт её звук (:func:`torrcast.adapters.stream_pack.spot_out.spot_out`);
        под старым куском копии больше нет, и перекод поверх него взял бы звук у него же -
        то есть у той самой рваной сетки, ради которой всё и затевалось. Копию возвращает
        обычный заход прогрева, одним прогоном и одним непрерывным звуком.

        Зовётся ОДИН раз, когда каталог заводят (:func:`torrcast.usecases.playback._warmer._warmer`),
        а не при выдаче: прогретое читается показом первым, и проверка на этом пути стоила бы
        чтения куска на каждый запрос.
        """
        if _lay(self.dir) == self.lay:
            return ()
        gone = tuple(_spot_marks(self.dir))
        for slot in gone:
            self.reject(slot)
        if gone:
            self.touch()
        return gone

    def reject(self, slot: int) -> None:
        """Убрать забракованный кусок вместе с меткой точечного перекода."""
        with contextlib.suppress(OSError):
            self.path(slot).unlink(missing_ok=True)
        with contextlib.suppress(OSError):
            self.spot(slot).unlink(missing_ok=True)

    def touch(self) -> None:
        with contextlib.suppress(OSError):
            (self.dir / META).write_text(
                json.dumps(
                    {
                        "key": self.key,
                        "title": self.title,
                        "at": _state._environment.epoch(),
                        "lay": self.lay,
                    }
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
