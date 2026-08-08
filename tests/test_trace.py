"""Недельный след: схема записей, ротация, потолок места и главный инвариант -
запись сегмента не делает синхронного I/O в горячем пути отдачи.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

import pytest

from torrcast import trace


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждый тест - свой каталог следа и свой sid: ленты тестов не смешиваются."""
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "test-sid")


def _read_lines(directory: Path) -> list[dict]:
    rows: list[dict] = []
    for path in sorted(directory.glob("trace-*.jsonl")):
        for raw in path.read_text("utf-8").splitlines():
            rows.append(json.loads(raw))
    return rows


def test_emit_schema(tmp_path: Path) -> None:
    """Запись несёт обязательный конверт и переданные поля, читается как JSON."""
    trace.emit("search", "query", query="матрица", raw=17)
    trace.shutdown()
    rows = _read_lines(tmp_path)
    assert len(rows) == 1
    rec = rows[0]
    assert rec["phase"] == "search"
    assert rec["event"] == "query"
    assert rec["sid"] == "test-sid"
    assert rec["query"] == "матрица"
    assert rec["raw"] == 17
    assert isinstance(rec["at"], float)
    assert isinstance(rec["pid"], int)


def test_records_reads_and_orders(tmp_path: Path) -> None:
    """`records` собирает ленту по каталогу и сортирует по времени, фильтруя по `since`."""
    trace.emit("play", "segment", slot=1)
    trace.emit("play", "segment", slot=2)
    trace.shutdown()
    time.sleep(0.05)  # больше миллисекундного округления времени записи
    cut = time.time()
    time.sleep(0.05)
    trace.emit("play", "segment", slot=3)
    trace.shutdown()
    assert [r["slot"] for r in trace.records()] == [1, 2, 3]
    recent = trace.records(since=cut)
    assert [r["slot"] for r in recent] == [3]


def test_bad_field_dropped_not_raised(tmp_path: Path) -> None:
    """Несериализуемое поле роняет запись, но не показ: emit не бросает."""
    trace.emit("play", "segment", bad=object())
    trace.shutdown()
    assert _read_lines(tmp_path) == []


# --- ротация и потолок места ------------------------------------------------


def test_rotation_drops_old_days(tmp_path: Path) -> None:
    """Сутки старше семи - сносятся при первой же записи; свежие остаются."""
    old = tmp_path / (f"trace-{time.strftime('%Y%m%d', time.localtime(time.time() - 30 * 86400))}"
                      ".jsonl")
    old.write_text('{"x":1}\n', encoding="utf-8")
    young = tmp_path / (f"trace-{time.strftime('%Y%m%d', time.localtime(time.time() - 2 * 86400))}"
                        ".jsonl")
    young.write_text('{"x":1}\n', encoding="utf-8")
    trace.emit("search", "query")
    trace.shutdown()
    assert not old.exists()
    assert young.exists()


def test_size_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Свыше потолка места самые старые сутки сносятся, свежие - остаются."""
    monkeypatch.setattr(trace, "MAX_BYTES", 100)
    now = time.time()
    days = [time.strftime("%Y%m%d", time.localtime(now - n * 86400)) for n in (5, 4, 3, 2, 1)]
    for day in days:
        (tmp_path / f"trace-{day}.jsonl").write_text("x" * 80, encoding="utf-8")
    trace.emit("search", "query")  # запишет сегодняшний файл и запустит ротацию
    trace.shutdown()
    left = sorted(p.name for p in tmp_path.glob("trace-*.jsonl"))
    total = sum(p.stat().st_size for p in tmp_path.glob("trace-*.jsonl"))
    assert total <= trace.MAX_BYTES
    # Сегодняшний (самый свежий) обязан уцелеть, самые старые - уйти.
    assert f"trace-{time.strftime('%Y%m%d', time.localtime(now))}.jsonl" in left
    assert f"trace-{days[0]}.jsonl" not in left


# --- ГЛАВНЫЙ ИНВАРИАНТ: горячий путь не ждёт журнал --------------------------


def test_put_does_no_synchronous_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`put` в горячем пути не трогает диск: ни ``os.open``, ни ``os.write``.

    Прямое доказательство инварианта. Глушим запуск фонового потока, чтобы всё, что делает
    put, было именно тем, что делает горячий путь, - и считаем обращения к диску: их ноль.
    Диск трогается только по явному drain, то есть в фоне.
    """
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setattr(trace._Writer, "_start", lambda self: None)  # поток не поднимаем
    import os as _os

    touched: list[str] = []
    monkeypatch.setattr(_os, "open", lambda *a, **k: touched.append("open") or 3)  # type: ignore[arg-type,return-value]
    monkeypatch.setattr(_os, "write", lambda *a, **k: touched.append("write") or 0)

    writer = trace._Writer()
    for i in range(500):
        writer.put({"phase": "play", "event": "segment", "slot": i})
    assert touched == [], "укладка записи сделала синхронный I/O - инвариант нарушен"
    assert writer._q.qsize() == 500  # всё лежит в очереди, а не на диске


def test_flush_runs_off_the_caller_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Запись на диск идёт в другом потоке, а не в том, что зовёт emit из горячего цикла."""
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    caller = threading.get_ident()
    flusher: list[int] = []
    real_flush = trace._Writer._flush

    def spy(self: trace._Writer, batch: list[dict]) -> None:
        flusher.append(threading.get_ident())
        real_flush(self, batch)

    monkeypatch.setattr(trace._Writer, "_flush", spy)
    writer = trace._Writer()
    began = time.perf_counter()
    for i in range(200):
        writer.put({"phase": "play", "event": "segment", "slot": i})
    hot_cost = time.perf_counter() - began
    writer.stop()  # дожать хвост
    assert flusher, "писатель ни разу не слил batch"
    assert all(tid != caller for tid in flusher), "слив шёл в потоке, зовущем put"
    # Горячий путь на 200 укладок обязан быть дешёвым: это очередь, а не диск.
    assert hot_cost < 0.5


def test_segment_emit_no_disk(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Врезка в отдачу сегмента ходит через тот же неблокирующий emit.

    Считаем синхронные ``os.write`` за время самого emit: их должно быть ноль - диск
    трогает только фоновый поток, дожатый затем shutdown.
    """
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "seg")
    import os as _os

    writes: list[int] = []
    real_write = _os.write

    def counting_write(fd: int, data: bytes) -> int:
        writes.append(fd)
        return real_write(fd, data)

    monkeypatch.setattr(_os, "write", counting_write)
    monkeypatch.setattr(trace._Writer, "_start", lambda self: None)  # поток не поднимаем
    writer = trace._Writer()
    for slot in range(50):
        writer.put({"phase": "play", "event": "segment", "slot": slot, "mb": 3.1})
    assert writes == [], "укладка сегмента сделала синхронный write - это регресс инварианта"
    writer.stop()  # thread не поднимался - stop дожимает синхронно через drain
    assert writes, "после дожатия хвост так и не записался"


def test_digest_summarises_session(tmp_path: Path) -> None:
    """Выжимка сводит сеанс: запрос, взятый релиз, ребуферы, обрывы, итог."""
    trace.emit("search", "query", query="матрица")
    trace.emit("search", "indexers", got={"rutor": 40, "nnm": 12}, silent=["kinozal"])
    trace.emit("select", "drop", release=1, why="av1")
    trace.emit("select", "select", release=2, quality="1080p", track="Дубляж", mbit=11.0)
    trace.emit("play", "buffering", pos=120.0)
    trace.emit("play", "buffering", pos=300.0)
    trace.emit("play", "offline", why="источник молчит")
    trace.emit("session", "session_end", pos=5400.0, dur=6000.0, watched=False)
    trace.shutdown()
    text = trace.digest(trace.records(), limit=3)
    assert "матрица" in text
    assert "rutor:40" in text and "kinozal" in text
    assert "av1" in text
    assert "1080p" in text
    assert "ребуферов 2" in text
    assert "обрывов сети 1" in text
    assert "остановлено" in text
