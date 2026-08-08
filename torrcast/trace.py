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
    "digest",
    "emit",
    "log_dir",
    "log_path",
    "records",
    "session_id",
    "shutdown",
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


def _session_block(sid: str, rows: list[dict[str, Any]]) -> str:
    began = float(rows[0].get("at", 0.0))
    lines: list[str] = []
    query = next((r for r in rows if r.get("event") == "query"), None)
    title = query.get("query") if query else None
    head = f"сеанс {_clock(began)}"
    if title:
        head += f" · «{title}»"
    lines.append(head)
    for rec in rows:
        line = _event_line(rec, began)
        if line:
            lines.append("  " + line)
    rebuffers = sum(1 for r in rows if r.get("event") == "buffering")
    offline = sum(1 for r in rows if r.get("event") == "offline")
    tail = f"  итог: ребуферов {rebuffers}"
    if offline:
        tail += f", обрывов сети {offline}"
    end = next((r for r in reversed(rows) if r.get("event") == "session_end"), None)
    if end is not None:
        where = _hms(float(end.get("pos", 0.0)))
        dur = float(end.get("dur", 0.0))
        watched = end.get("watched")
        state = "досмотрено" if watched else f"остановлено на {where}"
        tail += f"; {state}" + (f" из {_hms(dur)}" if dur and not watched else "")
    lines.append(tail)
    return "\n".join(lines)


def _event_line(rec: dict[str, Any], began: float) -> str:
    at = float(rec.get("at", 0.0)) - began
    stamp = f"+{at:6.1f}с "
    event = rec.get("event", "")
    if event == "indexers":
        got = rec.get("got") or {}
        silent = rec.get("silent") or []
        parts = ", ".join(f"{name}:{count}" for name, count in got.items())
        tail = f"; молчат {', '.join(map(str, silent))}" if silent else ""
        return f"{stamp}индексеры {parts or '-'}{tail}"
    if event == "select":
        return (
            f"{stamp}взят релиз {rec.get('release', '?')}"
            f" · {rec.get('quality', '?')} · {rec.get('track', '?')}"
            f" · ~{rec.get('mbit', '?')} Мбит/с"
        )
    if event == "drop":
        return f"{stamp}отброшен релиз {rec.get('release', '?')}: {rec.get('why', '?')}"
    if event == "note":
        return f"{stamp}{rec.get('text', '')}"
    if event == "buffering":
        return f"{stamp}ребуфер на {_hms(float(rec.get('pos', 0.0)))}"
    if event == "offline":
        return f"{stamp}сеть: {rec.get('why', 'обрыв')}"
    if event == "error":
        return f"{stamp}ошибка: {rec.get('text', '')}"
    if event == "session_start":
        return f"{stamp}показ «{rec.get('title', '')}» с {_hms(float(rec.get('pos', 0.0)))}"
    return ""
