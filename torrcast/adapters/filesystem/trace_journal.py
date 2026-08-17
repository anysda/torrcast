"""Недельный диагностический след: один структурированный ``jsonl`` рядом с состоянием.

Зачем отдельный слой, а не ещё один ``print``: то, что нужно для разбора сеанса, уже
пишется, но врозь и недолго. Фазы старта живут в секундомере (:func:`torrcast.timing.mark`),
время отдачи кусков - в ``TORRCAST_TRACE`` (:meth:`torrcast.stream._Handler._sent`), решения
отбора - в журнале прогресса (:meth:`torrcast.console.Progress.note`) и в ``journald`` юнита
показа. Каждое из этого гаснет вместе с командой и по нему нельзя спросить «что было за
неделю». Этот слой ничего из перечисленного не дублирует: он сводит те же события в одну
ленту - :func:`mark` и :func:`~torrcast.console.Progress.note` дозывают :func:`emit` сами,
- и держит её семь дней с потолком места.

🔴 **Запись не в горячем пути.** Отдача сегмента (:meth:`torrcast.stream._Handler._serve`)
зовёт :func:`emit`, а он только кладёт запись в очередь без единого обращения к диску:
пишет её на диск отдельный фоновый поток (:class:`_Writer`). Показ не ждёт ни ``open``, ни
``write``, ни ``flush`` - это проверяется тестом (``tests/test_trace.py``).

Всё локально: лента лежит там же, где состояние, никакой внешней системы. Разбор - команда
``cast log`` (:func:`digest`), она же читает :func:`records`.

🔴 **Слепая зона ленты.** Плата за то, что показ не ждёт диск, - конечная очередь: когда
фоновый писатель отстаёт, запись роняется (:meth:`_Writer.put`). Молча это больше не
происходит - потери считаются и уходят в ленту записью ``lost``, и ``cast log`` её печатает,
- но САМИ потерянные события не восстановимы. Читать ленту рядом с такой записью надо с
поправкой: пропуск там значит «съедено очередью», а не «этого не было».
"""

from __future__ import annotations

import contextlib
import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Any, Final

from torrcast.domain.trace_digest import digest
from torrcast.domain.trace_sources import WARMED

__all__ = [
    "LOG_ENV",
    "SID_ENV",
    "dark",
    "digest",
    "emit",
    "evict",
    "health",
    "log_dir",
    "log_path",
    "nudge",
    "plan",
    "records",
    "reload",
    "revive",
    "seek",
    "segment",
    "session_id",
    "shutdown",
    "skew",
    "start_session",
    "warmth",
]

#: Переопределение каталога ленты (тесты, локальный запуск). Пусто - рядом с состоянием.
LOG_ENV: Final = "TORRCAST_LOG"
#: Общий идентификатор сеанса у команды и у юнита показа. Ставится в окружение и едет в
#: юнит вместе с прочими путями (:data:`torrcast.stream._PASS_ENV`), поэтому поиск, отбор и
#: показ одного ``cast`` сводятся в одну строку истории.
SID_ENV: Final = "TORRCAST_SID"

#: Держим след неделю и не даём ему съесть диск.
RETAIN_DAYS: Final = 7
MAX_BYTES: Final = 64 * 1024 * 1024

_PREFIX: Final = "trace-"
_SUFFIX: Final = ".jsonl"
#: Очередь ограничена: если фоновый писатель отстаёт, запись роняется, но показ - никогда.
_QUEUE_MAX: Final = 4096
_BATCH: Final = 256
_session_seq = 0
_session_root = ""
_last_session = ""


def log_dir() -> Path:
    """Каталог ленты: ``TORRCAST_LOG`` или каталог файла состояния."""
    override = os.environ.get(LOG_ENV)
    if override:
        return Path(override)
    from torrcast.adapters.filesystem.state import state_path

    return state_path().parent


def log_path(when: float | None = None) -> Path:
    """Файл ленты за сутки ``when`` (по умолчанию - сегодня). Ротация - по суткам."""
    day = time.strftime("%Y%m%d", time.localtime(when))
    return log_dir() / f"{_PREFIX}{day}{_SUFFIX}"


def session_id() -> str:
    """Идентификатор сеанса; лениво создаётся и кэшируется в окружении под :data:`SID_ENV`."""
    sid = os.environ.get(SID_ENV)
    if not sid:
        sid = f"{int(time.time())}-{os.getpid()}"
        os.environ[SID_ENV] = sid
    return sid


def start_session() -> str:
    """Начать отдельный сеанс показа и вернуть его идентификатор.

    Вызывается один раз на границе фильма или серии, не из горячего пути. Родительский
    идентификатор сохраняет связь с вызовом ``cast``, суффикс не даёт сериям склеиться.
    """
    global _last_session, _session_root, _session_seq
    current = os.environ.get(SID_ENV, "")
    if current != _last_session:
        _session_root = current or f"{int(time.time())}-{os.getpid()}"
        _session_seq = 0
    _session_seq += 1
    sid = f"{_session_root}.{_session_seq}"
    os.environ[SID_ENV] = sid
    _last_session = sid
    return sid


class _Writer:
    """Фоновая запись ленты: :meth:`put` только кладёт в очередь, диск трогает :meth:`_run`.

    Разнесено намеренно - :meth:`put` зовут из горячего пути отдачи сегмента, и он обязан
    вернуться, не дожидаясь ни ``open``, ни ``flush``. Поток - демон: показ гасится, недопи-
    санный хвост ленты значения не имеет, а :func:`shutdown` при штатном выходе его дожимает.
    """

    def __init__(self) -> None:
        #: В очереди лежит не запись, а ПАРА «файл ленты, запись»: см. :meth:`put`.
        self._q: queue.Queue[tuple[Path, dict[str, Any]] | None] = queue.Queue(maxsize=_QUEUE_MAX)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pruned = ""
        #: Сколько записей очередь не приняла. Счётчик без замка НАМЕРЕННО: он про уже
        #: сломавшийся случай, а цена в горячем пути обязана остаться нулевой - недосчёт
        #: на гонке дешевле замка в отдаче сегмента.
        self._lost = 0

    def put(self, record: dict[str, Any]) -> None:
        """ГОРЯЧИЙ ПУТЬ. Ровно одно: неблокирующая укладка в очередь. Ни байта на диск.

        🔴 СЛЕПАЯ ЗОНА. Очередь конечна (:data:`_QUEUE_MAX`), и переполнение роняет запись:
        показ важнее диагностики. Молча это больше не делается - потери считаются и уходят
        в ленту отдельной записью (``lost``), которую печатает и ``cast log``. Но и запись о
        потере не всесильна: сами потерянные события не восстановимы, и «в ленте нет строки»
        рядом с ``lost`` значит «строка могла быть съедена очередью», а не «события не было».

        Файл ленты выбирается ЗДЕСЬ и едет в очереди вместе с записью. Место записи - это
        свойство МОМЕНТА СОБЫТИЯ, а не момента, когда до диска дошли руки: писатель
        фоновый, между укладкой и записью проходит сколько угодно времени, и за это время
        каталог ленты (:data:`LOG_ENV`, файл состояния) может смениться, а сутки -
        перевалить за полночь. Выбирай файл писатель у себя, отставший хвост уезжал бы в
        чужую ленту. Диска это не касается: :func:`log_path` только считает путь.
        """
        if self._thread is None:
            self._start()
        try:
            self._q.put_nowait((log_path(), record))
        except queue.Full:
            self._lost += 1

    def _start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            thread = threading.Thread(target=self._run, name="torrcast-trace", daemon=True)
            thread.start()
            self._thread = thread

    def _run(self) -> None:
        while True:
            first = self._q.get()
            if first is None:
                return
            batch: list[tuple[Path, dict[str, Any]]] = [first]
            with contextlib.suppress(queue.Empty):
                while len(batch) < _BATCH:
                    nxt = self._q.get_nowait()
                    if nxt is None:
                        self._flush(batch)
                        return
                    batch.append(nxt)
            self._flush(batch)

    def drain(self) -> None:
        """Синхронно записать всё, что уже в очереди. Для :func:`shutdown` и тестов."""
        batch: list[tuple[Path, dict[str, Any]]] = []
        with contextlib.suppress(queue.Empty):
            while True:
                item = self._q.get_nowait()
                if item is not None:
                    batch.append(item)
        if batch or self._lost:  # признание в потерях дожимается даже с пустым хвостом
            self._flush(batch)

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            self.drain()
            return
        self._q.put(None)
        thread.join(timeout=2.0)
        self._thread = None

    def _flush(self, batch: list[tuple[Path, dict[str, Any]]]) -> None:
        lost, self._lost = self._lost, 0
        if lost:
            # Переполнение очереди - единственный способ потерять решение уже ПОСЛЕ того,
            # как о нём сказали человеку. Признаваться в этом обязана сама лента: иначе
            # разбор недели уверенно прочитает пропуск как «события не было». Своего файла
            # у признания нет - потерянные записи в очередь не попали, - поэтому оно
            # ложится к первой записи пакета, то есть к соседям по потерянному месту.
            confession = {
                "at": round(time.time(), 3),
                "sid": session_id(),
                "pid": os.getpid(),
                "phase": "trace",
                "event": "lost",
                "count": lost,
            }
            batch = [(batch[0][0] if batch else log_path(), confession), *batch]
        # Обычно файл у всего пакета один и запись выходит одна, как раньше. Разные файлы
        # в одном пакете - это смена каталога ленты на ходу: тогда каждая запись едет
        # туда, куда собиралась, а не туда, где писателя застала эта смена.
        pending: dict[Path, list[dict[str, Any]]] = {}
        for path, record in batch:
            pending.setdefault(path, []).append(record)
        for path, records_ in pending.items():
            blob = "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in records_)
            with contextlib.suppress(OSError):
                path.parent.mkdir(parents=True, exist_ok=True)
                # O_APPEND и одна запись на файл: две ноги (команда и юнит) пишут в тот же
                # файл, атомарная дозапись держит строки целыми - как в секундомере старта.
                fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
                try:
                    os.write(fd, blob.encode("utf-8"))
                finally:
                    os.close(fd)
        for directory in dict.fromkeys(path.parent for path in pending):
            self._prune(directory)

    def _prune(self, directory: Path) -> None:
        """Ротация: старше семи суток - снести, свыше потолка места - снести самые старые.

        Раз в сутки на каталог: чаще незачем, а на каждый пакет - лишние ``stat``. Ключ
        несёт и каталог: сменился путь ленты (``TORRCAST_LOG``) - ротация идёт по новому.
        """
        today = f"{directory}:{time.strftime('%Y%m%d')}"
        if self._pruned == today:
            return
        self._pruned = today
        with contextlib.suppress(OSError):
            files = sorted(directory.glob(f"{_PREFIX}*{_SUFFIX}"))
            cutoff = time.strftime("%Y%m%d", time.localtime(time.time() - RETAIN_DAYS * 86400))
            kept: list[Path] = []
            for path in files:
                day = path.name[len(_PREFIX) : -len(_SUFFIX)]
                if day < cutoff:
                    path.unlink(missing_ok=True)
                else:
                    kept.append(path)
            total = 0
            for path in reversed(kept):  # даты сортируются хронологически, новые - в хвосте
                with contextlib.suppress(OSError):
                    total += path.stat().st_size
                    if total > MAX_BYTES:
                        path.unlink(missing_ok=True)


_writer = _Writer()


def emit(phase: str, event: str, **fields: Any) -> None:
    """Положить событие в недельный след. Не блокирует и не пишет на диск сам.

    ``phase`` - крупная фаза (``search``/``select``/``play``/``warm``/``timeline``/
    ``note``/``session``/``error``), ``event`` - конкретное событие внутри неё. Остальное -
    поля события: числа, строки, короткие списки. Всё, что не сериализуется в JSON, роняется
    вместе с записью - диагностика не имеет права ронять показ.
    """
    record: dict[str, Any] = {
        "at": round(time.time(), 3),
        "sid": session_id(),
        "pid": os.getpid(),
        "phase": phase,
        "event": event,
    }
    record.update(fields)
    try:
        json.dumps(record, ensure_ascii=False)
    except (TypeError, ValueError):
        return
    _writer.put(record)


def shutdown() -> None:
    """Дожать хвост ленты на штатном выходе. Без вызова хвост теряется - и это допустимо."""
    _writer.stop()


# --- схема событий ----------------------------------------------------------
# Имена полей живут ЗДЕСЬ, а не по местам вызова: место вызова знает свои числа, а как
# они называются в ленте и как читаются в `cast log` - дело этого модуля. Каждая функция
# ниже - это и объявление полей, и единственный способ их поставить; печать той же записи
# лежит рядом, в :func:`_event_line`. Все они, как и :func:`emit`, только кладут запись в
# очередь: ни одна не имеет права ждать диск, даже если зовут её не из горячего пути.


def nudge(pos: float, to: float, hit: int, stuck: float, front: float) -> None:
    """Сторож расшевелил зависший приёмник: где стоял, куда прыгнули, каким по счёту.

    ``stuck`` - сколько секунд позиция не двигалась, ``front`` - докуда было упаковано
    (по нему видно, зависание это было или законное ожидание упаковки).
    """
    emit(
        "play",
        "nudge",
        pos=round(pos, 1),
        to=round(to, 1),
        hit=hit,
        stuck=round(stuck, 1),
        front=round(front, 1),
    )


def segment(slot: int, mb: float, sent: float, wait: float, src: str) -> None:
    """Отданный приёмнику кусок: номер, вес, время отдачи, ожидание и ИСТОЧНИК.

    ``src`` - :data:`PACKED` или :data:`WARMED`. Без него в ленте не отличить кусок живой
    упаковки от прогретого, а это разные производители: разойдись у них решение о
    кодировании - и на стыке декодер приёмника переинициализируется. Стыки считает
    :func:`digest`, поэтому поле стоит в каждой записи, а не только на переходах: по одним
    переходам нельзя сказать, чем шёл показ между ними.

    🔴 Зовётся из горячего пути отдачи (:meth:`torrcast.stream._Handler._log_segment`):
    только :func:`emit`, то есть только укладка в очередь.
    """
    emit(
        "play",
        "segment",
        slot=slot,
        mb=round(mb, 2),
        sent=round(sent, 3),
        wait=round(wait, 3),
        src=src,
    )


def plan(pack: str, warm: str, spots: int, preset: str = "", mbit: float = 0.0) -> None:
    """Чем кодирует куски живая упаковка и чем - прогрев, один раз на показ.

    ``pack``/``warm`` - ``copy`` или ``recode``; ``spots`` - сколько кусков перекодируются
    точечно (тяжёлые). Запись существует ради одного вопроса: одинаково ли решают два
    производителя кусков одного показа. Разошлись - это видно строкой в ``cast log``, а не
    разбором аргументов ffmpeg постфактум.
    """
    emit("warm", "plan", pack=pack, warm=warm, spots=spots, preset=preset, mbit=round(mbit, 2))


def reload(pos: float, tries: int, error: int | None = None) -> None:
    """Повтор LOAD посреди показа: приёмник отвалился и его подняли заново."""
    emit("play", "reload", pos=round(pos, 1), tries=tries, error=error)


def offline(why: str, asked: bool = False) -> None:
    """Источник перестал читаться: чем это объясняется и спрашивали ли самого источника.

    ``asked`` - правда ли причину назвал сам источник (:meth:`torrcast.stream.Origin.trouble`),
    а не догадка по мёртвому прогону упаковки. Разница существенная: «упаковка оборвалась»
    и «служба раздач не отвечает» выглядят в показе одинаково, а значат разное, и в следе
    это должно быть видно без гадания.
    """
    emit("play", "offline", why=why, asked=asked)


def resupply(torrent: str, ok: bool) -> None:
    """Раздачу вернули МАГНИТОМ после аварии источника: чью и удалось ли.

    ``torrent`` - хэш нашей раздачи (чужих не трогаем), ``ok`` - вернулась ли она под тем
    же хэшем. Событие про трекеры: URL потока несёт только хэш, и служба, пережившая
    перезапуск, заводит по нему раздачу без трекеров - ноль байт при живом рое.
    """
    emit("play", "resupply", torrent=torrent, ok=ok)


def dark(pos: float, why: str, shown: bool = True) -> None:
    """Показ погас: приёмник бросил его насовсем, на экране пусто.

    ``pos`` - место фильма, где это случилось (оно же сохранено в состоянии), ``why`` -
    что показ знал о беде в тот момент (обрыв источника или молчаливый отказ приёмника).

    ``shown`` - видел ли зритель хоть один кадр ДО этой темноты. Две разные аварии, и
    считать их одной нельзя: погасший показ человек успел посмотреть, а показ, не давший
    ни кадра, - это «включил и не включилось», самая дорогая беда лестницы цели. По этому
    полю они и разделяются в недельном разборе.
    """
    emit("play", "dark", pos=round(pos, 1), why=why, shown=shown)


def revive(pos: float, tries: int, waited: float, ok: bool) -> None:
    """Попытка поднять погасший показ: откуда, какая по счёту, после скольких секунд темноты.

    ``ok`` - взял ли приёмник LOAD. Ложь тут не хуже правды: по ней и видно, сколько раз
    воскрешение не удалось, прежде чем показ погас честно.
    """
    emit("play", "revive", pos=round(pos, 1), tries=tries, waited=round(waited, 1), ok=ok)


def seek(frm: float, to: float, wait: float | None, why: str = "") -> None:
    """Перемотка: откуда, куда и сколько секунд ждали КАРТИНКУ после неё.

    Ожидание меряется до сдвига указателя с места приземления, а не до слова ``PLAYING``:
    приёмник говорит его раньше первого кадра (:attr:`torrcast.cast.ChromecastReceiver.
    PICTURE_STEP`). ``wait=None`` - картинки после этой перемотки не случилось вовсе, и
    ``why`` называет, чем всё кончилось.
    """
    extra = {"why": why} if why else {}
    emit(
        "play",
        "seek",
        frm=round(frm, 1),
        to=round(to, 1),
        wait=None if wait is None else round(wait, 2),
        **extra,
    )


def evict(key: str, freed: int, need: int, title: str = "") -> None:
    """Бюджет прогрева вытеснил чужой каталог: кого, сколько байт освободил и подо что."""
    emit("warm", "evict", key=key, title=title, freed=freed, need=need)


def skew(slot: int, want: float, got: float, hole: bool, src: str = WARMED) -> None:
    """Уложенный кусок разошёлся со своей границей сетки: где, на сколько и чем кончилось.

    ``want`` - граница сетки, ``got`` - где кусок начинается на самом деле, ``off`` -
    разница (отрицательная: назад). ``hole`` - место признано непрогретым, ложь - кусок
    выброшен и перекладывается заново. ``src`` - тот же источник куска, что и в
    :func:`segment`: сверяется пока только прогретое, но событие про УКЛАДКУ, а не про
    прогрев, и по одному полю видно, чьё производство промахнулось.

    Событие существует ради истории: дефект укладки мимо сетки жил незамеченным, потому
    что выглядел здоровым выборочно (:meth:`torrcast.warm.Warmer._verify`). Строка в
    журнале показа гаснет вместе с ним, а эта запись лежит неделю - по ней видно, что
    сторож срабатывал, сколько раз и на каких местах.
    """
    emit(
        "warm",
        "skew",
        slot=slot,
        want=round(want, 3),
        got=round(got, 3),
        off=round(got - want, 3),
        hole=hole,
        src=src,
    )


def warmth(event: str, secs: float, dur: float, size: int, why: str = "") -> None:
    """Доля прогретого на этот момент: секунды на диске, длина фильма, доля и вес.

    ``event`` - ``ready`` (фильм лёг целиком) или ``stall`` (прогрев встал, причина - в
    ``why``). Доля считается здесь, чтобы читатель ленты её не пересчитывал.
    """
    emit(
        "warm",
        event,
        secs=round(secs),
        dur=round(dur),
        share=round(secs / dur, 3) if dur > 0 else 0.0,
        size=size,
        why=why,
    )


def health() -> tuple[bool, float, int]:
    """Здоровье самой ленты: есть ли она, когда писали последний раз, сколько весит.

    Возвращает ``(есть, время последней записи, байт всего)``; время - ``0.0``, если
    ленты нет. Файлы читаются по ``stat``, содержимое не разбирается: строка в
    ``cast doctor`` отвечает на «пишется ли след», а не «что в нём».
    """
    newest, total, found = 0.0, 0, False
    with contextlib.suppress(OSError):
        for path in log_dir().glob(f"{_PREFIX}*{_SUFFIX}"):
            with contextlib.suppress(OSError):
                stat = path.stat()
                found = True
                total += stat.st_size
                newest = max(newest, stat.st_mtime)
    return found, newest, total


def records(since: float = 0.0) -> list[dict[str, Any]]:
    """Лента за все сутки в каталоге, по возрастанию времени, не раньше ``since``."""
    found: list[dict[str, Any]] = []
    with contextlib.suppress(OSError):
        for path in sorted(log_dir().glob(f"{_PREFIX}*{_SUFFIX}")):
            with contextlib.suppress(OSError):
                for raw in path.read_text("utf-8").splitlines():
                    # Нечитаемая строка значит «этой строки нет» и ничего больше. Разбор и
                    # проверка стоят под одним suppress намеренно: врозь неразобранная
                    # строка оставляла в `rec` ПРЕДЫДУЩУЮ запись, и та уходила в выдачу
                    # вторым разом, а битая первая строка роняла `cast log` целиком. Хвост
                    # ленты рвётся законно: писатель - демон, и последняя запись может
                    # оборваться на середине вместе с погашенным показом.
                    with contextlib.suppress(TypeError, ValueError):
                        rec = json.loads(raw)
                        if isinstance(rec, dict) and float(rec.get("at", 0.0)) >= since:
                            found.append(rec)
    return sorted(found, key=lambda e: float(e.get("at", 0.0)))


class FileJournal:
    """Лента как объект: тот же файл и тот же фоновый писатель, но за портом.

    Модульные функции ниже остаются на месте - их зовут щупы и совместимый фасад
    :mod:`torrcast.trace`, - а слои получают этот объект от композиционного корня
    (:mod:`torrcast.runtime.wire`) и знают только договор :class:`~torrcast.ports.
    journal.Journal`.
    """

    emit = staticmethod(emit)
    shutdown = staticmethod(shutdown)
    records = staticmethod(records)
    session_id = staticmethod(session_id)
    start_session = staticmethod(start_session)
    health = staticmethod(health)
    nudge = staticmethod(nudge)
    segment = staticmethod(segment)
    plan = staticmethod(plan)
    reload = staticmethod(reload)
    offline = staticmethod(offline)
    resupply = staticmethod(resupply)
    dark = staticmethod(dark)
    revive = staticmethod(revive)
    seek = staticmethod(seek)
    evict = staticmethod(evict)
    skew = staticmethod(skew)
    warmth = staticmethod(warmth)
