"""Недельный след: схема записей, ротация, потолок места и главный инвариант -
запись сегмента не делает синхронного I/O в горячем пути отдачи.
"""

from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

import pytest

from tests.fakes.clock import FakeClock
from torrcast import trace
from torrcast.adapters.filesystem.trace_journal import prune as _prune_module
from torrcast.adapters.filesystem.trace_journal import writer as _writer_module
from torrcast.domain.digest import _seams


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждый тест - свой каталог следа и свой sid: ленты тестов не смешиваются."""
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "test-sid")


def _read_lines(directory: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
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


def test_two_show_sessions_are_unambiguously_selected_in_one_log(tmp_path: Path) -> None:
    """Две серии одного вызова получают разные метки и не смешиваются при отборе."""
    first = trace.start_session()
    trace.emit("session", "session_start", title="первая", pos=0.0)
    trace.emit("play", "buffering", pos=12.0)
    trace.emit("session", "session_end", pos=60.0, dur=60.0, watched=True)
    second = trace.start_session()
    trace.emit("session", "session_start", title="вторая", pos=0.0)
    trace.emit("play", "buffering", pos=34.0)
    trace.emit("session", "session_end", pos=50.0, dur=50.0, watched=True)
    trace.shutdown()

    rows = trace.records()
    selected = [row for row in rows if row["sid"] == first]
    journal = [
        f"[сеанс {first}] экран: 0:12 из 1:00 · BUFFERING",
        f"[сеанс {second}] экран: 0:34 из 0:50 · BUFFERING",
    ]
    shown = [line for line in journal if f"[сеанс {first}]" in line]
    assert first != second
    assert [row["event"] for row in selected] == ["session_start", "buffering", "session_end"]
    assert {row["sid"] for row in selected} == {first}
    assert shown == [f"[сеанс {first}] экран: 0:12 из 1:00 · BUFFERING"]
    digest = trace.digest(rows, limit=0)
    assert f"сеанс {first}" in digest and f"сеанс {second}" in digest
    assert digest.count("итог: ребуферов 1; досмотрено") == 2


def test_show_start_prints_effective_thresholds_and_their_sources(tmp_path: Path) -> None:
    trace.emit(
        "session",
        "session_start",
        title="проверка",
        pos=0.0,
        profile="androidtv",
        profile_source="паспорт приёмника",
        thresholds={"recode_at_mbit": 28.0, "recode_head_wait": 12.0},
        threshold_sources={
            "recode_at_mbit": "профиль androidtv",
            "recode_head_wait": "написан в конфиге",
        },
    )
    trace.shutdown()

    text = trace.digest(trace.records())
    assert "профиль androidtv (паспорт приёмника)" in text
    assert "recode_at_mbit=28.0 [профиль androidtv]" in text
    assert "recode_head_wait=12.0 [написан в конфиге]" in text


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
    old = tmp_path / (
        f"trace-{time.strftime('%Y%m%d', time.localtime(time.time() - 30 * 86400))}.jsonl"
    )
    old.write_text('{"x":1}\n', encoding="utf-8")
    young = tmp_path / (
        f"trace-{time.strftime('%Y%m%d', time.localtime(time.time() - 2 * 86400))}.jsonl"
    )
    young.write_text('{"x":1}\n', encoding="utf-8")
    trace.emit("search", "query")
    trace.shutdown()
    assert not old.exists()
    assert young.exists()


def test_size_ceiling(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Свыше потолка места самые старые сутки сносятся, свежие - остаются."""
    monkeypatch.setattr(_prune_module, "MAX_BYTES", 100)
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


def test_оборванная_строка_ленты_не_задваивает_соседнюю(tmp_path: Path) -> None:
    """Строка, которую не разобрать, значит «этой строки нет» - и ничего больше.

    Хвост ленты рвётся законно: писатель - демон, и последняя запись обрывается
    на середине вместе с погашенным показом. Читатель обязан молча пройти мимо -
    а он подсовывал вместо неё ПРЕДЫДУЩУЮ запись вторым разом (и падал целиком,
    если рваной оказывалась первая строка). Задвоенное решение в разборе недели
    хуже пропущенного: пропуск видно, а повтор читается как «так и было».
    """
    whole = [
        {"at": 100.0, "sid": "s", "phase": "search", "event": "query", "query": "матрица"},
        {"at": 200.0, "sid": "s", "phase": "select", "event": "select", "release": 2},
    ]
    lines = [json.dumps(rec, ensure_ascii=False) for rec in whole]
    torn = lines[0][:20]  # запись, оборванная на полуслове

    (tmp_path / "trace-20250101.jsonl").write_text("\n".join([*lines, torn]) + "\n", "utf-8")
    assert trace.records() == whole, "оборванный хвост задвоил соседнюю запись"

    (tmp_path / "trace-20250101.jsonl").write_text("\n".join([torn, *lines]) + "\n", "utf-8")
    assert trace.records() == whole, "рваная ПЕРВАЯ строка уронила чтение ленты"

    # Мусор на месте времени - тот же случай: строка нечитаемая, лента - нет.
    (tmp_path / "trace-20250101.jsonl").write_text(
        "\n".join([json.dumps({"at": "никогда", "event": "query"}), *lines]) + "\n", "utf-8"
    )
    assert trace.records() == whole


# --- ГЛАВНЫЙ ИНВАРИАНТ: горячий путь не ждёт журнал --------------------------


def test_put_does_no_synchronous_io(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`put` в горячем пути не трогает диск: ни ``os.open``, ни ``os.write``.

    Прямое доказательство инварианта. Глушим запуск фонового потока, чтобы всё, что делает
    put, было именно тем, что делает горячий путь, - и считаем обращения к диску: их ноль.
    Диск трогается только по явному drain, то есть в фоне.
    """
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setattr(_writer_module._Writer, "_start", lambda self: None)  # поток не поднимаем
    import os as _os

    touched: list[str] = []

    def fake_open(*_a: object, **_k: object) -> int:
        touched.append("open")
        return 3

    def fake_write(*_a: object, **_k: object) -> int:
        touched.append("write")
        return 0

    monkeypatch.setattr(_os, "open", fake_open)
    monkeypatch.setattr(_os, "write", fake_write)

    writer = _writer_module._Writer()
    for i in range(500):
        writer.put({"phase": "play", "event": "segment", "slot": i})
    assert touched == [], "укладка записи сделала синхронный I/O - инвариант нарушен"
    assert writer._q.qsize() == 500  # всё лежит в очереди, а не на диске


def test_flush_runs_off_the_caller_thread(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Запись на диск идёт в другом потоке, а не в том, что зовёт emit из горячего цикла."""
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    caller = threading.get_ident()
    flusher: list[int] = []
    real_flush = _writer_module._Writer._flush

    def spy(self: _writer_module._Writer, batch: list[tuple[Path, dict[str, object]]]) -> None:
        flusher.append(threading.get_ident())
        real_flush(self, batch)

    monkeypatch.setattr(_writer_module._Writer, "_flush", spy)
    writer = _writer_module._Writer()
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
    monkeypatch.setattr(_writer_module._Writer, "_start", lambda self: None)  # поток не поднимаем
    writer = _writer_module._Writer()
    for slot in range(50):
        writer.put({"phase": "play", "event": "segment", "slot": slot, "mb": 3.1})
    assert writes == [], "укладка сегмента сделала синхронный write - это регресс инварианта"
    writer.stop()  # thread не поднимался - stop дожимает синхронно через drain
    assert writes, "после дожатия хвост так и не записался"


def test_отставший_хвост_не_дописывается_в_чужую_ленту(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запись едет в ту ленту, на которую журнал смотрел в МОМЕНТ СОБЫТИЯ.

    Обратная сторона неблокирующей укладки: между ``emit`` и попаданием записи на диск
    проходит сколько угодно времени, а каталог ленты за это время может смениться
    (:data:`trace.LOG_ENV`, файл состояния) или наступить новые сутки. Выбирай писатель
    файл у себя, отставший хвост дописывался бы в ленту, которую переменная показывает
    СЕЙЧАС, - в чужую. Дыра нашлась на полном прогоне: хвост соседнего теста попадал
    в каталог следующего, и тот находил у себя запись, которой взяться неоткуда.

    Писатель тут придержан на первой записи не ради скорости, а чтобы окно гонки было
    ровно тем самым: запись уже у писателя, но ещё не на диске.
    """
    first, second = tmp_path / "первая", tmp_path / "вторая"
    took, hold = threading.Event(), threading.Event()
    real_flush = _writer_module._Writer._flush

    def held(self: _writer_module._Writer, batch: list[tuple[Path, dict[str, object]]]) -> None:
        took.set()
        hold.wait(5.0)
        real_flush(self, batch)

    monkeypatch.setattr(_writer_module._Writer, "_flush", held)
    monkeypatch.setenv(trace.LOG_ENV, str(first))
    trace.emit("search", "query", query="первая")
    assert took.wait(5.0), "писатель так и не взял запись - окно гонки не воспроизведено"
    monkeypatch.setenv(trace.LOG_ENV, str(second))
    trace.emit("search", "query", query="вторая")
    hold.set()
    trace.shutdown()

    assert [rec["query"] for rec in _read_lines(first)] == ["первая"]
    assert [rec["query"] for rec in _read_lines(second)] == ["вторая"], (
        "хвост отставшего писателя дописался в чужую ленту"
    )


def test_digest_summarises_session(tmp_path: Path) -> None:
    """Выжимка сводит сеанс: запрос, взятый релиз, ребуферы, обрывы, итог."""
    trace.emit("search", "query", query="матрица")
    trace.emit(
        "search",
        "indexers",
        got={"rutor": 40, "nnm": 12},
        silent=["kinozal"],
        ms={"rutor": 412, "nnm": 890, "kinozal": 20031},
    )
    trace.emit("select", "drop", release=1, why="av1")
    trace.emit("select", "select", release=2, quality="1080p", track="Дубляж", mbit=11.0)
    trace.emit("play", "buffering", pos=120.0)
    trace.emit("play", "buffering", pos=300.0)
    trace.emit("play", "offline", why="источник молчит")
    trace.emit("session", "session_end", pos=5400.0, dur=6000.0, watched=False)
    trace.shutdown()
    text = trace.digest(trace.records(), limit=3)
    assert "матрица" in text
    assert "rutor:40 за 0.4 с" in text and "kinozal за 20.0 с" in text
    assert "av1" in text
    assert "1080p" in text
    assert "ребуферов 2" in text
    assert "обрывов сети 1" in text
    assert "остановлено" in text


# --- поля вместо текста: нуджи сторожа, вытеснения прогрева, перемотки ---------


def _only(rows: list[dict[str, object]], event: str) -> dict[str, object]:
    found = [rec for rec in rows if rec.get("event") == event]
    assert len(found) == 1, f"событий «{event}» в ленте {len(found)}, а не одно"
    return found[0]


class _FakeController:
    def __init__(self, jumps: list[float]) -> None:
        self.jumps = jumps

    def seek(self, pos: float) -> None:
        self.jumps.append(pos)


class _FakeDevice:
    def __init__(self, jumps: list[float]) -> None:
        self.media_controller = _FakeController(jumps)


class _Reported:
    """MEDIA_STATUS, как его отдаёт приёмник: позиция, состояние, длительность."""

    def __init__(self, pos: float, state: str = "PLAYING") -> None:
        self.current_time = pos
        self.player_state = state
        self.idle_reason = None
        self.duration = 5977.0
        self.player_is_playing = state in {"PLAYING", "BUFFERING"}


def test_a_nudge_is_a_record_with_numbers_not_a_line_of_text(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Нудж сторожа виден в ленте полями: где стоял, куда прыгнул, каким по счёту.

    До этого о нудже можно было узнать только по косвенным признакам - ребуфер в ленте
    есть, а лечили его или нет, не сказано. Разбор недельного следа обязан отвечать на
    «сколько раз приёмник пришлось расшевелить и на каких местах фильма».
    """
    from torrcast.cast import ChromecastReceiver

    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice([]))
    receiver = ChromecastReceiver("10.0.0.50")
    receiver._peak = 84.0
    receiver._nudge(84.0, front=144.0)  # первый неподвижный тик - ещё не зависание
    receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
    receiver._nudge(84.0, front=144.0)
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "nudge")
    assert rec["phase"] == "play"
    assert rec["pos"] == 84.0
    assert rec["to"] == 84.0 + ChromecastReceiver.STALL_SKIP
    assert rec["hit"] == 1
    assert rec["front"] == 144.0
    assert float(str(rec["stuck"])) >= ChromecastReceiver.STALL_SECONDS
    text = trace.digest(trace.records())
    assert "нудж сторожа 1" in text and "1:24 -> 1:32" in text
    assert "нуджей сторожа 1" in text


def test_a_reload_of_a_dead_receiver_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Повтор LOAD - тоже событие показа: на какой секунде отвалились и какая это попытка."""
    from torrcast.cast import ChromecastReceiver

    receiver = ChromecastReceiver("10.0.0.50")
    receiver._peak = 4355.0
    monkeypatch.setattr(ChromecastReceiver, "_restart_app", lambda self: None)
    monkeypatch.setattr(ChromecastReceiver, "_load", lambda self, at=0.0: None)
    assert receiver._reload()
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "reload")
    assert rec["pos"] == 4355.0
    assert rec["tries"] == 1
    assert "повтор LOAD 1" in trace.digest(trace.records())


def test_a_seek_carries_where_to_and_how_long_the_picture_took(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Перемотка - событие с полями, а не фаза таймлайна.

    Приёмник мотает сам, команды нам при этом не приходит, поэтому перемотку видно только
    по прыжку позиции. Ценность записи - в том, что было ПОСЛЕ: сколько человек смотрел на
    чёрный экран, пока показ снова не поехал.
    """
    from torrcast.cast import ChromecastReceiver

    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice([]))
    receiver = ChromecastReceiver("10.0.0.50")
    script = [
        _Reported(600.0),  # смотрим 10:00
        _Reported(1891.0, "BUFFERING"),  # пультом на 31:31 - картинки ещё нет
        _Reported(1891.0, "BUFFERING"),
        _Reported(1893.0),  # поехало
    ]
    monkeypatch.setattr(ChromecastReceiver, "_status", lambda self: script.pop(0))
    for _ in range(4):
        receiver.position(front=1e6)
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "seek")
    assert rec["frm"] == 600.0
    assert rec["to"] == 1891.0
    assert float(str(rec["wait"])) >= 0.0
    text = trace.digest(trace.records())
    assert "перемотка 10:00 -> 31:31" in text
    assert "картинка через" in text
    assert "перемоток 1" in text


def test_a_seek_is_measured_to_the_moving_pointer_not_to_the_word_playing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ожидание после перемотки меряется до КАДРА, а не до слова приёмника.

    ``PLAYING`` приходит раньше первого кадра: указатель после прыжка стоит на месте
    приземления, пока приёмник не наберёт буфер. Метрика, верившая слову, записала в ленту
    0.0 с у всех трёх прыжков подряд - при том что картинка возвращалась за 6.0, 5.9 и
    9.9 с, и «перемотка стала быстрее» после этого измеряло бы не то.
    """
    from torrcast.cast import ChromecastReceiver

    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice([]))
    clock = FakeClock()
    receiver = ChromecastReceiver("10.0.0.50", clock=clock)
    # Все пробы в PLAYING нарочно: ровно так и врал приёмник на живом Q70D.
    script = [
        _Reported(600.0),  # смотрим 10:00
        _Reported(1891.0),  # пультом на 31:31: слово есть, кадра нет
        _Reported(1891.0),  # указатель стоит - экран всё ещё чёрный
        _Reported(1891.0),
        _Reported(1893.0),  # тронулся - вот он, первый кадр
    ]
    monkeypatch.setattr(ChromecastReceiver, "_status", lambda self: script.pop(0))
    for tick in range(5):
        clock.now = 2.0 * tick
        receiver.position(front=1e6)
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "seek")
    assert rec["to"] == 1891.0
    assert rec["wait"] == 6.0, "ожидание отмерено от слова приёмника, а не от сдвига указателя"


def test_a_seek_that_never_showed_a_picture_is_a_record_and_not_a_silence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Перемотка, после которой кадра не случилось вовсе, пишется отдельным исходом.

    Ждать сдвига указателя вечно нельзя, а молчать о таком прыжке нельзя тем более:
    «нет строки в ленте» пришлось бы читать как «перемотки не было». Нулём же его писала
    ровно та метрика, которую чинят, - и худший исход выглядел бы как лучший.
    """
    from torrcast.cast import ChromecastReceiver

    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice([]))
    receiver = ChromecastReceiver("10.0.0.50")
    script = [
        _Reported(600.0),
        _Reported(1891.0, "BUFFERING"),  # прыжок принят, картинки ждём
        _Reported(0.0, "IDLE"),  # сессия умерла, ждать больше некого
    ]
    monkeypatch.setattr(ChromecastReceiver, "_status", lambda self: script.pop(0))
    for _ in range(3):
        receiver.position(front=1e6)
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "seek")
    assert rec["to"] == 1891.0
    assert rec["wait"] is None
    assert "картинки так и не было" in trace.digest(trace.records())


def test_our_own_nudge_is_not_counted_as_a_seek_by_the_viewer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Прыжок сторожа - не перемотка человека, и в ленте он ровно один раз, как нудж.

    Иначе разбор недели врёт дважды: каждый нудж считается ещё и перемоткой, а «человек
    мотает» перестаёт что-либо значить.
    """
    from torrcast.cast import ChromecastReceiver

    monkeypatch.setattr(ChromecastReceiver, "_device", lambda self: _FakeDevice([]))
    receiver = ChromecastReceiver("10.0.0.50")
    stuck = [_Reported(84.0, "BUFFERING") for _ in range(4)]
    # Прыжок сторожа растёт с каждой попыткой (8 · hits) и на третьей перерастает порог
    # перемотки - ровно тот случай, в котором нудж и мог сойти за человека с пультом.
    script = [*stuck, _Reported(108.0, "BUFFERING"), _Reported(110.0)]
    monkeypatch.setattr(ChromecastReceiver, "_status", lambda self: script.pop(0))
    receiver.position(front=1e6)  # первый неподвижный тик
    for _ in range(3):
        receiver._stall_since -= ChromecastReceiver.STALL_SECONDS
        receiver.position(front=1e6)  # нудж: 92, 100, 108
    receiver.position(front=1e6)  # приёмник доехал туда, куда его послал сторож
    receiver.position(front=1e6)
    trace.shutdown()

    rows = _read_lines(tmp_path)
    events = [r["event"] for r in rows if r["event"] in {"nudge", "seek"}]
    assert events == ["nudge", "nudge", "nudge"], "свой же прыжок записан как перемотка"


def test_a_dark_screen_and_its_revival_are_records_with_numbers(tmp_path: Path) -> None:
    """Погасший показ и его подъём - события ленты, а не только строки в журнале.

    Через неделю вопрос будет ровно один: сам ли показ пережил обрыв или человек ходил к
    консоли. Ответ обязан лежать полями: где погас, что показ знал о беде, сколько длилась
    темнота и взял ли приёмник LOAD с какой попытки.
    """
    trace.dark(pos=4355.0, why="источник молчит дольше 45 с")
    trace.revive(pos=4355.0, tries=1, waited=312.0, ok=False)
    trace.revive(pos=4355.0, tries=2, waited=374.0, ok=True)
    trace.shutdown()

    rows = _read_lines(tmp_path)
    dark = _only(rows, "dark")
    assert dark["phase"] == "play"
    assert dark["pos"] == 4355.0 and dark["why"] == "источник молчит дольше 45 с"
    ups = [r for r in rows if r["event"] == "revive"]
    assert [r["tries"] for r in ups] == [1, 2]
    assert [r["ok"] for r in ups] == [False, True]
    assert ups[1]["waited"] == 374.0
    text = trace.digest(trace.records())
    assert "показ погас на 1:12:35: источник молчит дольше 45 с" in text
    assert "приёмник показ не взял с 1:12:35 (попытка 1, темнота 312 с)" in text
    assert "показ поднят с 1:12:35 (попытка 2, темнота 374 с)" in text
    assert "погасаний показа 1" in text and "воскрешений показа 2" in text


def test_an_eviction_says_who_was_thrown_out_and_how_much_it_freed(tmp_path: Path) -> None:
    """Вытеснение из бюджета прогрева - запись с именем, названием и освобождёнными байтами.

    Это единственный случай, когда прогрев трогает ЧУЖОЕ, и через неделю вопрос будет
    ровно один: почему вчерашний фильм не открылся с диска. Ответ обязан лежать полями.
    """
    from torrcast.usecases.warm import META, Vault

    root = tmp_path / "warm"
    old = Vault(root=root, key="старый", budget=1000, floor=0, title="Тачки 3")
    old.open()
    old.path(0).write_bytes(b"x" * 400)
    os.utime(old.dir / META, (time.time() - 86400, time.time() - 86400))
    mine = Vault(root=root, key="мой", budget=1000, floor=0)
    mine.open()
    mine.path(0).write_bytes(b"x" * 400)

    assert mine.fit(300) == "", "место обязано найтись за счёт чужого"
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "evict")
    assert rec["phase"] == "warm"
    assert rec["key"] == "старый"
    assert rec["title"] == "Тачки 3"
    assert rec["freed"] == 400
    assert rec["need"] == 300
    assert "вытеснил «Тачки 3»" in trace.digest(trace.records())


def test_a_piece_laid_off_the_grid_is_a_record_with_numbers(tmp_path: Path) -> None:
    """Промах укладки мимо сетки - поля, а не строка: где, на сколько, чем кончилось.

    Дефект укладки мимо сетки прожил незамеченным неделями
    (:meth:`torrcast.usecases.warm.Warmer._verify`),
    и вопрос через неделю будет ровно один: срабатывал ли сторож и на каких местах. Ответ
    обязан лежать числами - границей, фактическим началом и разницей между ними, - а не
    печататься в журнал показа, который гаснет вместе с ним.
    """
    trace.skew(slot=7, want=88.0, got=86.29, hole=True)
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "skew")
    assert rec["phase"] == "warm"
    assert rec["slot"] == 7
    assert rec["want"] == 88.0
    assert rec["got"] == 86.29
    assert rec["off"] == -1.71, "разница обязана лежать полем, а не считаться читателем"
    assert rec["hole"] is True
    assert rec["src"] == trace.WARMED, "источник куска назван не так, как в записи отдачи"
    text = trace.digest(trace.records())
    assert "v7 лёг мимо сетки" in text and "место осталось непрогретым" in text
    assert "кусков мимо сетки 1" in text


def test_the_share_of_the_warmed_movie_is_a_field(tmp_path: Path) -> None:
    """Доля прогретого уходит в ленту числами, а не строкой «прогрето 42 мин из 96».

    Строка остаётся человеку в живом показе; недельному разбору нужны секунды, длина
    фильма, доля и вес каталога - по ним видно, докуда дошёл прогрев и почему встал.
    """
    from torrcast.adapters.stream_pack.grid import Grid
    from torrcast.usecases.warm import Vault, Warmer

    grid = Grid.uniform(100.0)
    vault = Vault(root=tmp_path / "warm", key="k", budget=1 << 30, floor=0)
    vault.open()
    for slot in range(3):
        vault.path(slot).write_bytes(b"x" * 1024)
    warmer = Warmer(source="clip", audio=0, grid=grid, vault=vault, log=lambda _line: None)
    warmer._stall("бюджет диска 20 ГБ исчерпан")
    trace.shutdown()

    rec = _only(_read_lines(tmp_path), "stall")
    assert rec["phase"] == "warm"
    assert rec["dur"] == 100
    assert rec["secs"] == round(warmer.warmed)
    assert rec["share"] == round(warmer.warmed / 100.0, 3)
    assert rec["size"] == 3 * 1024
    assert rec["why"] == "бюджет диска 20 ГБ исчерпан"
    assert "прогрев встал: бюджет диска 20 ГБ исчерпан" in trace.digest(trace.records())


def test_the_new_fields_never_break_an_old_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Лента, записанная ДО этих полей, обязана читаться `cast log` как читалась.

    Разбор старых записей - не украшение: недельный след затем и держат неделю, чтобы
    вчерашний сеанс пережил сегодняшнее обновление. Здесь - запись ровно того формата,
    который был до добора полей, плюс событие, о котором эта версия не знает вовсе.
    """
    from torrcast import cli

    old = [
        {
            "at": time.time() - 120,
            "sid": "вчера",
            "pid": 7,
            "phase": "search",
            "event": "query",
            "query": "матрица",
            "raw": 17,
        },
        {
            "at": time.time() - 110,
            "sid": "вчера",
            "pid": 7,
            "phase": "play",
            "event": "buffering",
            "pos": 120.0,
        },
        {
            "at": time.time() - 100,
            "sid": "вчера",
            "pid": 7,
            "phase": "play",
            "event": "нечто",
            "чего-мы-не-знаем": 1,
        },
        {
            "at": time.time() - 90,
            "sid": "вчера",
            "pid": 7,
            "phase": "session",
            "event": "session_end",
            "pos": 5400.0,
            "dur": 6000.0,
            "watched": False,
        },
    ]
    path = tmp_path / f"trace-{time.strftime('%Y%m%d')}.jsonl"
    path.write_text(
        "".join(json.dumps(rec, ensure_ascii=False) + "\n" for rec in old), encoding="utf-8"
    )

    assert cli.main(["log"]) == 0
    text = capsys.readouterr().out
    assert "матрица" in text
    assert "ребуфер на 2:00" in text
    assert "ребуферов 1" in text and "нуджей" not in text
    assert "остановлено на 1:30:00" in text


def test_cast_log_shows_the_new_events(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Сквозная проверка: события легли в ленту - и `cast log` их напечатал."""
    from torrcast import cli

    trace.emit("search", "query", query="тачки")
    trace.nudge(pos=84.0, to=92.0, hit=1, stuck=9.0, front=144.0)
    trace.seek(frm=600.0, to=1891.0, wait=3.2)
    trace.evict(key="k", freed=4_200_000_000, need=1_000_000_000, title="Тачки 3")
    trace.warmth("ready", secs=2520.0, dur=5760.0, size=6_000_000_000)
    trace.shutdown()

    assert cli.main(["log"]) == 0
    text = capsys.readouterr().out
    assert "нудж сторожа 1: 1:24 -> 1:32 (стоял 9 с, готово впереди 60 с)" in text
    assert "перемотка 10:00 -> 31:31, картинка через 3.2 с" in text
    assert "бюджет прогрева вытеснил «Тачки 3»: освободилось 4.2 ГБ под 1.0 ГБ" in text
    assert "прогрето 42:00 из 1:36:00 (44 %, 6.0 ГБ)" in text
    assert "нуджей сторожа 1, перемоток 1, вытеснений прогрева 1" in text


def test_doctor_says_whether_the_journal_is_alive(tmp_path: Path) -> None:
    """`cast doctor` отвечает и про сам след: есть ли он, свежий ли, сколько весит.

    Пустая лента ломает не показ, а разбор: узнать, что писать было некуда, надо до того,
    как понадобится вчерашний сеанс, - поэтому «внимание», а не «плохо».
    """
    from torrcast.usecases.doctor import _trace

    line, ok = _trace()
    assert ok, "отсутствие следа - не отказ показа"
    assert "следа нет" in line

    trace.emit("search", "query", query="матрица")
    trace.shutdown()
    line, ok = _trace()
    assert ok
    assert "след" in line and "МБ" in line and "последняя запись" in line


def test_a_served_piece_says_which_producer_made_it(tmp_path: Path) -> None:
    """Кусок в ленте несёт ИСТОЧНИК: живая упаковка или прогретое.

    Без этого поля разбор упирался в слепую зону: по записи видно вес и время отдачи, но
    не видно, чей это кусок, - а куски одного показа делают два разных производителя, и
    расхождение между ними приёмник ловит именно на стыке.
    """
    monkey = pytest.MonkeyPatch()
    monkey.setenv(trace.LOG_ENV, str(tmp_path))
    monkey.setenv(trace.SID_ENV, "src")
    trace.segment(slot=40, mb=3.1, sent=0.4, wait=0.02, src=trace.PACKED)
    trace.segment(slot=41, mb=2.9, sent=0.3, wait=0.01, src=trace.WARMED)
    trace.shutdown()
    rows = [r for r in trace.records() if r.get("event") == "segment"]
    monkey.undo()

    assert [r["src"] for r in rows] == ["pack", "warm"], "источник куска в ленту не попал"
    assert rows[0]["slot"] == 40 and rows[0]["mb"] == 3.1, "прежние поля записи потерялись"
    seams = _seams(rows)
    assert [r["slot"] for r in seams] == [41], "смена производителя посреди показа не видна"
    assert "стыков источника 1" in trace.digest(rows), "выжимка молчит про стык источников"
    assert "источник сменился на прогретое" in trace.digest(rows), "стык не назван"


def test_the_source_field_costs_the_hot_path_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Врезка источника не имеет права трогать диск: :func:`trace.segment` - тот же put."""
    monkeypatch.setenv(trace.LOG_ENV, str(tmp_path))
    monkeypatch.setenv(trace.SID_ENV, "hot")
    trace.shutdown()
    import os as _os

    writes: list[int] = []
    real_write = _os.write

    def counting_write(fd: int, data: bytes) -> int:
        writes.append(fd)
        return real_write(fd, data)

    monkeypatch.setattr(_os, "write", counting_write)
    monkeypatch.setattr(_writer_module._Writer, "_start", lambda self: None)  # поток не поднимаем
    for slot in range(200):
        trace.segment(slot=slot, mb=3.0, sent=0.1, wait=0.0, src=trace.WARMED)

    assert writes == [], "запись источника сделала синхронный write - регресс инварианта"


def test_the_plan_says_how_both_producers_encode(tmp_path: Path) -> None:
    """Решение о кодировании - строка ленты, а не разбор аргументов ffmpeg постфактум."""
    monkey = pytest.MonkeyPatch()
    monkey.setenv(trace.LOG_ENV, str(tmp_path))
    monkey.setenv(trace.SID_ENV, "plan")
    trace.plan(pack="copy", warm="copy", spots=5, preset="veryfast", mbit=9.0)
    trace.shutdown()
    rows = [r for r in trace.records() if r.get("event") == "plan"]
    monkey.undo()

    assert rows[0]["pack"] == "copy" and rows[0]["warm"] == "copy", "решения в ленте нет"
    assert rows[0]["spots"] == 5, "точечный перекод не сосчитан"
    assert "упаковка - копия, прогрев - копия" in trace.digest(rows), "выжимка молчит о решении"


# --- 🔴 TC-194: в выжимке видны ВСЕ классы записанных событий -----------------


def test_cast_log_shows_the_timeline_and_the_query(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Фазы критического пути и запрос пишутся в ленту всегда - и обязаны печататься.

    🔴 TC-194. До этого `cast log` не рендерил их вовсе: своей ветки у события нет,
    :func:`torrcast.domain.digest._event_line` возвращала пустую строку, и целый
    класс записей, лежащих в
    ``jsonl``, человек не видел. Это ровно та ловушка, ради которой след и заведён: «в
    журнале нет строки» читалось как «события не было».
    """
    from torrcast import cli
    from torrcast.adapters.filesystem.stopwatch import mark

    trace.emit("search", "query", query="сталкер", raw=41, pictures=3)
    mark("отбор релиза", релиз=2)
    mark("упаковка пошла")
    mark("упаковка пошла")  # фаза повторяется: у показа их бывают десятки
    trace.emit("session", "session_end", pos=60.0, dur=120.0, watched=False)
    trace.shutdown()

    assert cli.main(["log"]) == 0
    text = capsys.readouterr().out
    assert "запрос «сталкер»: строк 41, картин 3" in text
    assert "фаза «отбор релиза» (релиз=2)" in text
    assert "фаза «упаковка пошла», всего 2" in text
    assert text.count("фаза «упаковка пошла»") == 1, "повтор фазы не имеет права съесть выжимку"
    assert "session_end" not in text, "конец сеанса печатает итоговая строка, и только она"
    assert "остановлено на 1:00" in text


def test_an_event_this_version_does_not_know_is_printed_anyway(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Событие без своей ветки печатается полями, а не пропадает.

    Лента живёт неделю и переживает обновления: запись соседней ветки или прошлой версии
    обязана быть видна хотя бы как есть. Молчание тут - худший из возможных ответов.
    """
    from torrcast import cli

    trace.emit("play", "нечто", чего_мы_не_знаем=1)
    trace.shutdown()

    assert cli.main(["log"]) == 0
    assert "play/нечто (чего_мы_не_знаем=1)" in capsys.readouterr().out


def test_records_eaten_by_a_full_queue_are_confessed_and_not_hidden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Слепая зона названа вслух: переполненная очередь роняет записи и говорит сколько.

    Плата за то, что показ не ждёт диск, - конечная очередь
    (:data:`~torrcast.adapters.filesystem.trace_journal._QUEUE_MAX`).
    Записи при этом теряются, и восстановить их нечем; но молчать о самой потере нельзя -
    иначе разбор недели уверенно прочитает дыру как «решений не было».
    """
    monkeypatch.setattr(_writer_module, "_QUEUE_MAX", 2)
    monkeypatch.setattr(_writer_module._Writer, "_start", lambda self: None)  # поток не поднимаем
    writer = _writer_module._Writer()
    for slot in range(10):
        writer.put({"phase": "play", "event": "segment", "slot": slot, "sid": "test-sid"})
    writer.stop()  # thread не поднимался - stop дожимает синхронно через drain

    rows = _read_lines(tmp_path)
    lost = [rec for rec in rows if rec.get("event") == "lost"]
    assert len(lost) == 1, "о потере сказано ровно один раз на пакет"
    assert lost[0]["count"] == 8, "восемь записей очередь не приняла - столько и признано"
    assert len([r for r in rows if r.get("event") == "segment"]) == 2
    assert "потеряно записей 8" in trace.digest(trace.records())
