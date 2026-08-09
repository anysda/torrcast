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


def log_dir() -> Path:
    """Каталог ленты: ``TORRCAST_LOG`` или каталог файла состояния."""
    override = os.environ.get(LOG_ENV)
    if override:
        return Path(override)
    from torrcast.state import state_path

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


class _Writer:
    """Фоновая запись ленты: :meth:`put` только кладёт в очередь, диск трогает :meth:`_run`.

    Разнесено намеренно - :meth:`put` зовут из горячего пути отдачи сегмента, и он обязан
    вернуться, не дожидаясь ни ``open``, ни ``flush``. Поток - демон: показ гасится, недопи-
    санный хвост ленты значения не имеет, а :func:`shutdown` при штатном выходе его дожимает.
    """

    def __init__(self) -> None:
        self._q: queue.Queue[dict[str, Any] | None] = queue.Queue(maxsize=_QUEUE_MAX)
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._pruned = ""

    def put(self, record: dict[str, Any]) -> None:
        """ГОРЯЧИЙ ПУТЬ. Ровно одно: неблокирующая укладка в очередь. Ни байта на диск."""
        if self._thread is None:
            self._start()
        with contextlib.suppress(queue.Full):
            self._q.put_nowait(record)

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
            batch = [first]
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
        batch: list[dict[str, Any]] = []
        with contextlib.suppress(queue.Empty):
            while True:
                item = self._q.get_nowait()
                if item is not None:
                    batch.append(item)
        if batch:
            self._flush(batch)

    def stop(self) -> None:
        thread = self._thread
        if thread is None:
            self.drain()
            return
        self._q.put(None)
        thread.join(timeout=2.0)
        self._thread = None

    def _flush(self, batch: list[dict[str, Any]]) -> None:
        path = log_path()
        blob = "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in batch)
        with contextlib.suppress(OSError):
            path.parent.mkdir(parents=True, exist_ok=True)
            # O_APPEND и одна запись на пакет: две ноги (команда и юнит) пишут в тот же файл,
            # атомарная дозапись держит строки целыми - как в секундомере старта.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
            try:
                os.write(fd, blob.encode("utf-8"))
            finally:
                os.close(fd)
        self._prune(path.parent)

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


#: Откуда взялся отданный кусок. Имена короткие, потому что поле идёт в КАЖДОЙ записи
#: сегмента: ``pack`` - живая упаковка показа, ``warm`` - прогретое на диске.
PACKED: Final = "pack"
WARMED: Final = "warm"


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


def reload(pos: float, tries: int) -> None:
    """Повтор LOAD посреди показа: приёмник отвалился и его подняли заново."""
    emit("play", "reload", pos=round(pos, 1), tries=tries)


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


def dark(pos: float, why: str) -> None:
    """Показ погас: приёмник бросил его насовсем, на экране пусто.

    ``pos`` - место фильма, где это случилось (оно же сохранено в состоянии), ``why`` -
    что показ знал о беде в тот момент (обрыв источника или молчаливый отказ приёмника).
    """
    emit("play", "dark", pos=round(pos, 1), why=why)


def revive(pos: float, tries: int, waited: float, ok: bool) -> None:
    """Попытка поднять погасший показ: откуда, какая по счёту, после скольких секунд темноты.

    ``ok`` - взял ли приёмник LOAD. Ложь тут не хуже правды: по ней и видно, сколько раз
    воскрешение не удалось, прежде чем показ погас честно.
    """
    emit("play", "revive", pos=round(pos, 1), tries=tries, waited=round(waited, 1), ok=ok)


def seek(frm: float, to: float, wait: float) -> None:
    """Перемотка: откуда, куда и сколько секунд ждали картинку после неё."""
    emit("play", "seek", frm=round(frm, 1), to=round(to, 1), wait=round(wait, 2))


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
                    with contextlib.suppress(ValueError):
                        rec = json.loads(raw)
                    if isinstance(rec, dict) and float(rec.get("at", 0.0)) >= since:
                        found.append(rec)
    return sorted(found, key=lambda e: float(e.get("at", 0.0)))


def _hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _clock(at: float) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(at))


def digest(rows: list[dict[str, Any]], limit: int = 3) -> str:
    """Читаемая выжимка последних сеансов: что искали, что взяли, ребуферы и ошибки.

    Сеанс - все записи с одним ``sid`` (:func:`session_id` держит его общим у команды и
    юнита). Порядок - от свежих; ``limit`` ограничивает число сеансов, ``0`` - все.
    """
    if not rows:
        return "следа нет - за неделю ни одного сеанса"
    order: list[str] = []
    by_sid: dict[str, list[dict[str, Any]]] = {}
    for rec in rows:
        sid = str(rec.get("sid", "?"))
        if sid not in by_sid:
            by_sid[sid] = []
            order.append(sid)
    for rec in rows:
        by_sid[str(rec.get("sid", "?"))].append(rec)
    order.sort(key=lambda s: float(by_sid[s][-1].get("at", 0.0)), reverse=True)
    if limit > 0:
        order = order[:limit]
    blocks = [_session_block(sid, by_sid[sid]) for sid in order]
    return "\n\n".join(blocks)


def _seams(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Записи сегментов, на которых сменился источник (:func:`segment`).

    Первый кусок сеанса стыком не считается: у него нет предыдущего источника, а «показ
    начался с прогретого» - не стык, а начало. Пустой список значит ровно «в ленте нет
    записей с полем ``src``» ИЛИ «источник за весь сеанс не менялся»: эти два случая
    различаются наличием самих записей сегментов, и путать их нельзя.
    """
    found: list[dict[str, Any]] = []
    previous = ""
    for rec in rows:
        if rec.get("event") != "segment":
            continue
        src = str(rec.get("src", ""))
        if not src:
            continue
        if previous and src != previous:
            found.append(rec)
        previous = src
    return found


def _session_block(sid: str, rows: list[dict[str, Any]]) -> str:
    began = float(rows[0].get("at", 0.0))
    lines: list[str] = []
    query = next((r for r in rows if r.get("event") == "query"), None)
    title = query.get("query") if query else None
    head = f"сеанс {_clock(began)}"
    if title:
        head += f" · «{title}»"
    lines.append(head)
    seams = {id(rec) for rec in _seams(rows)}
    for rec in rows:
        line = _event_line(rec, began, seam=id(rec) in seams)
        if line:
            lines.append("  " + line)
    counts = {name: sum(1 for r in rows if r.get("event") == name) for name in _COUNTED}
    tail = f"  итог: ребуферов {counts['buffering']}"
    if seams:
        tail += f", стыков источника {len(seams)}"
    for name, word in _COUNTED.items():
        if name != "buffering" and counts[name]:
            tail += f", {word} {counts[name]}"
    end = next((r for r in reversed(rows) if r.get("event") == "session_end"), None)
    if end is not None:
        where = _hms(float(end.get("pos", 0.0)))
        dur = float(end.get("dur", 0.0))
        watched = end.get("watched")
        state = "досмотрено" if watched else f"остановлено на {where}"
        tail += f"; {state}" + (f" из {_hms(dur)}" if dur and not watched else "")
    lines.append(tail)
    return "\n".join(lines)


#: Что считается в итоговой строке сеанса и как это называется по-русски. Ребуферы
#: печатаются всегда (ноль ребуферов - тоже новость), остальное - только когда было.
_COUNTED: Final = {
    "buffering": "ребуферов",
    "offline": "обрывов сети",
    "resupply": "возвратов раздачи магнитом",
    "dark": "погасаний показа",
    "revive": "воскрешений показа",
    "nudge": "нуджей сторожа",
    "reload": "повторов LOAD",
    "seek": "перемоток",
    "evict": "вытеснений прогрева",
    "skew": "кусков мимо сетки",
}


#: Решение о кодировании куска по-русски (:func:`plan`).
_PLAN: Final = {"copy": "копия", "recode": "перекод"}


def _gb(size: float) -> str:
    return f"{size / 1e9:.1f} ГБ"


#: Как называется источник куска в выжимке.
_SOURCES: Final = {PACKED: "живая упаковка", WARMED: "прогретое"}


def _event_line(rec: dict[str, Any], began: float, seam: bool = False) -> str:
    at = float(rec.get("at", 0.0)) - began
    stamp = f"+{at:6.1f}с "
    event = rec.get("event", "")
    if event == "segment":
        # Каждый кусок в выжимку не печатаем - их сотни; печатаем только смену источника.
        if not seam:
            return ""
        src = str(rec.get("src", ""))
        return f"{stamp}v{rec.get('slot', '?')}: источник сменился на {_SOURCES.get(src, src)}"
    if event == "plan":
        spots = int(rec.get("spots", 0))
        tail = f", точечный перекод {spots}" if spots else ""
        return (
            f"{stamp}куски: упаковка - {_PLAN.get(str(rec.get('pack', '')), '?')},"
            f" прогрев - {_PLAN.get(str(rec.get('warm', '')), '?')}{tail}"
        )
    if event == "indexers":
        got = rec.get("got") or {}
        silent = rec.get("silent") or []
        took = rec.get("ms") or {}

        def _took(name: object) -> str:
            # Время держим за именем: «за 0.4 с» после счётчика, у молчунов - вместо него.
            # В записях прежних версий поля ms нет вовсе - тогда строка выглядит как раньше.
            ms = took.get(str(name)) if isinstance(took, dict) else None
            return f" за {float(ms) / 1000:.1f} с" if ms is not None else ""

        parts = ", ".join(f"{name}:{count}{_took(name)}" for name, count in got.items())
        tail = f"; молчат {', '.join(str(name) + _took(name) for name in silent)}" if silent else ""
        return f"{stamp}индексеры {parts or '-'}{tail}"
    if event == "select":
        return (
            f"{stamp}взят релиз {rec.get('release', '?')}"
            f" · {rec.get('quality', '?')} · {rec.get('track', '?')}"
            f" · ~{rec.get('mbit', '?')} Мбит/с"
        )
    if event == "queue":
        # Отсев до очереди - свёрткой, а не событием на раздачу: их сотни на запрос.
        # Сумма очереди и причин обязана сходиться с пулом, и в строке это видно глазами.
        dropped = rec.get("dropped") or {}
        reasons = ", ".join(f"{name} {count}" for name, count in dropped.items())
        lost = sum(int(count) for count in dropped.values())
        head = f"{stamp}пул {rec.get('pool', '?')}: в очереди {rec.get('queued', '?')}"
        return f"{head}, выкинуто {lost}" + (f" ({reasons})" if reasons else "")
    if event == "runtime":
        # Знаменатель битрейта отбора: чем считали и откуда взяли (TC-185).
        got = "из справки" if rec.get("src") == "facts" else "прикидка: справка молчит"
        return f"{stamp}длительность {_hms(float(rec.get('secs', 0.0)))} - {got}"
    if event == "drop":
        return f"{stamp}отброшен релиз {rec.get('release', '?')}: {rec.get('why', '?')}"
    if event == "note":
        return f"{stamp}{rec.get('text', '')}"
    if event == "buffering":
        return f"{stamp}ребуфер на {_hms(float(rec.get('pos', 0.0)))}"
    if event == "offline":
        # Спрошенный источник называется источником: «сеть» тут была бы догадкой, а мы
        # знаем точно - служба ответила (или не ответила) нам сама.
        head = "источник" if rec.get("asked") else "сеть"
        return f"{stamp}{head}: {rec.get('why', 'обрыв')}"
    if event == "resupply":
        end = "раздача вернулась" if rec.get("ok") else "служба ещё не отдала раздачу"
        return f"{stamp}раздачу добавил магнитом заново - {end}"
    if event == "nudge":
        return (
            f"{stamp}нудж сторожа {rec.get('hit', 1)}:"
            f" {_hms(float(rec.get('pos', 0.0)))} -> {_hms(float(rec.get('to', 0.0)))}"
            f" (стоял {float(rec.get('stuck', 0.0)):.0f} с,"
            f" готово впереди {float(rec.get('front', 0.0)) - float(rec.get('pos', 0.0)):.0f} с)"
        )
    if event == "reload":
        return (
            f"{stamp}приёмник отвалился на {_hms(float(rec.get('pos', 0.0)))}"
            f" - повтор LOAD {rec.get('tries', 1)}"
        )
    if event == "dark":
        return (
            f"{stamp}показ погас на {_hms(float(rec.get('pos', 0.0)))}:"
            f" {rec.get('why', 'приёмник бросил показ')}"
        )
    if event == "revive":
        took = "показ поднят" if rec.get("ok") else "приёмник показ не взял"
        return (
            f"{stamp}{took} с {_hms(float(rec.get('pos', 0.0)))}"
            f" (попытка {rec.get('tries', 1)},"
            f" темнота {float(rec.get('waited', 0.0)):.0f} с)"
        )
    if event == "seek":
        return (
            f"{stamp}перемотка {_hms(float(rec.get('frm', 0.0)))}"
            f" -> {_hms(float(rec.get('to', 0.0)))},"
            f" картинка через {float(rec.get('wait', 0.0)):.1f} с"
        )
    if event == "evict":
        who = rec.get("title") or rec.get("key", "?")
        return (
            f"{stamp}бюджет прогрева вытеснил «{who}»:"
            f" освободилось {_gb(float(rec.get('freed', 0.0)))}"
            f" под {_gb(float(rec.get('need', 0.0)))}"
        )
    if event == "skew":
        end = "место осталось непрогретым" if rec.get("hole") else "кусок переложен заново"
        return (
            f"{stamp}v{rec.get('slot', '?')} лёг мимо сетки:"
            f" начало {float(rec.get('off', 0.0)):+.2f} с"
            f" от границы {_hms(float(rec.get('want', 0.0)))} - {end}"
        )
    if event in {"ready", "stall"}:
        head = (
            f"{stamp}прогрето {_hms(float(rec.get('secs', 0.0)))}"
            f" из {_hms(float(rec.get('dur', 0.0)))}"
            f" ({float(rec.get('share', 0.0)) * 100:.0f} %,"
            f" {_gb(float(rec.get('size', 0.0)))})"
        )
        why = rec.get("why")
        return f"{head} - прогрев встал: {why}" if why else head
    if event == "error":
        return f"{stamp}ошибка: {rec.get('text', '')}"
    if event == "session_start":
        # Профиль приёмника: по какому набору порогов играли. В записях прежних версий
        # его нет вовсе - тогда и в строке о нём молчим, а не пишем «профиль ?».
        profile = str(rec.get("profile", ""))
        head = f"{stamp}показ «{rec.get('title', '')}» с {_hms(float(rec.get('pos', 0.0)))}"
        return f"{head} · профиль {profile}" if profile else head
    return ""
