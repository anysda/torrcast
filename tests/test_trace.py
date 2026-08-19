"""Недельный след целиком: событие ложится на диск и читается ``cast log`` обратно.

Каждое звено меряется своим зеркалом рядом с ним
(``tests/adapters/filesystem/trace_journal/``); здесь остаётся то, что зеркалу одного
звена не принадлежит - сквозной путь от вызова до напечатанной выжимки.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal import (
    LOG_ENV,
    SID_ENV,
    dark,
    emit,
    evict,
    nudge,
    plan,
    records,
    revive,
    seek,
    segment,
    shutdown,
    skew,
    start_session,
    warmth,
)
from torrcast.cli.main import main
from torrcast.domain.digest import _seams, digest
from torrcast.domain.trace_sources import PACKED, WARMED


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Каждый тест - свой каталог следа и свой sid: ленты тестов не смешиваются."""
    monkeypatch.setenv(LOG_ENV, str(tmp_path))
    monkeypatch.setenv(SID_ENV, "test-sid")


def _read_lines(directory: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("trace-*.jsonl")):
        for raw in path.read_text("utf-8").splitlines():
            rows.append(json.loads(raw))
    return rows


def test_emit_schema(tmp_path: Path) -> None:
    """Запись несёт обязательный конверт и переданные поля, читается как JSON."""
    emit("search", "query", query="матрица", raw=17)
    shutdown()
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
    first = start_session()
    emit("session", "session_start", title="первая", pos=0.0)
    emit("play", "buffering", pos=12.0)
    emit("session", "session_end", pos=60.0, dur=60.0, watched=True)
    second = start_session()
    emit("session", "session_start", title="вторая", pos=0.0)
    emit("play", "buffering", pos=34.0)
    emit("session", "session_end", pos=50.0, dur=50.0, watched=True)
    shutdown()

    rows = records()
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
    text = digest(rows, limit=0)
    assert f"сеанс {first}" in text and f"сеанс {second}" in text
    assert text.count("итог: ребуферов 1; досмотрено") == 2


def test_show_start_prints_effective_thresholds_and_their_sources(tmp_path: Path) -> None:
    emit(
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
    shutdown()

    text = digest(records())
    assert "профиль androidtv (паспорт приёмника)" in text
    assert "recode_at_mbit=28.0 [профиль androidtv]" in text
    assert "recode_head_wait=12.0 [написан в конфиге]" in text


def test_records_reads_and_orders(tmp_path: Path) -> None:
    """`records` собирает ленту по каталогу и сортирует по времени, фильтруя по `since`."""
    emit("play", "segment", slot=1)
    emit("play", "segment", slot=2)
    shutdown()
    time.sleep(0.05)  # больше миллисекундного округления времени записи
    cut = time.time()
    time.sleep(0.05)
    emit("play", "segment", slot=3)
    shutdown()
    assert [r["slot"] for r in records()] == [1, 2, 3]
    recent = records(since=cut)
    assert [r["slot"] for r in recent] == [3]


def test_bad_field_dropped_not_raised(tmp_path: Path) -> None:
    """Несериализуемое поле роняет запись, но не показ: emit не бросает."""
    emit("play", "segment", bad=object())
    shutdown()
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
    emit("search", "query")
    shutdown()
    assert not old.exists()
    assert young.exists()


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
    assert records() == whole, "оборванный хвост задвоил соседнюю запись"

    (tmp_path / "trace-20250101.jsonl").write_text("\n".join([torn, *lines]) + "\n", "utf-8")
    assert records() == whole, "рваная ПЕРВАЯ строка уронила чтение ленты"

    # Мусор на месте времени - тот же случай: строка нечитаемая, лента - нет.
    (tmp_path / "trace-20250101.jsonl").write_text(
        "\n".join([json.dumps({"at": "никогда", "event": "query"}), *lines]) + "\n", "utf-8"
    )
    assert records() == whole


# --- ГЛАВНЫЙ ИНВАРИАНТ: горячий путь не ждёт журнал --------------------------


def test_digest_summarises_session(tmp_path: Path) -> None:
    """Выжимка сводит сеанс: запрос, взятый релиз, ребуферы, обрывы, итог."""
    emit("search", "query", query="матрица")
    emit(
        "search",
        "indexers",
        got={"rutor": 40, "nnm": 12},
        silent=["kinozal"],
        ms={"rutor": 412, "nnm": 890, "kinozal": 20031},
    )
    emit("select", "drop", release=1, why="av1")
    emit("select", "select", release=2, quality="1080p", track="Дубляж", mbit=11.0)
    emit("play", "buffering", pos=120.0)
    emit("play", "buffering", pos=300.0)
    emit("play", "offline", why="источник молчит")
    emit("session", "session_end", pos=5400.0, dur=6000.0, watched=False)
    shutdown()
    text = digest(records(), limit=3)
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


def test_a_dark_screen_and_its_revival_are_records_with_numbers(tmp_path: Path) -> None:
    """Погасший показ и его подъём - события ленты, а не только строки в журнале.

    Через неделю вопрос будет ровно один: сам ли показ пережил обрыв или человек ходил к
    консоли. Ответ обязан лежать полями: где погас, что показ знал о беде, сколько длилась
    темнота и взял ли приёмник LOAD с какой попытки.
    """
    dark(pos=4355.0, why="источник молчит дольше 45 с")
    revive(pos=4355.0, tries=1, waited=312.0, ok=False)
    revive(pos=4355.0, tries=2, waited=374.0, ok=True)
    shutdown()

    rows = _read_lines(tmp_path)
    blackout = _only(rows, "dark")
    assert blackout["phase"] == "play"
    assert blackout["pos"] == 4355.0 and blackout["why"] == "источник молчит дольше 45 с"
    ups = [r for r in rows if r["event"] == "revive"]
    assert [r["tries"] for r in ups] == [1, 2]
    assert [r["ok"] for r in ups] == [False, True]
    assert ups[1]["waited"] == 374.0
    text = digest(records())
    assert "показ погас на 1:12:35: источник молчит дольше 45 с" in text
    assert "приёмник показ не взял с 1:12:35 (попытка 1, темнота 312 с)" in text
    assert "показ поднят с 1:12:35 (попытка 2, темнота 374 с)" in text
    assert "погасаний показа 1" in text and "воскрешений показа 2" in text


def test_an_eviction_says_who_was_thrown_out_and_how_much_it_freed(tmp_path: Path) -> None:
    """Вытеснение из бюджета прогрева - запись с именем, названием и освобождёнными байтами.

    Это единственный случай, когда прогрев трогает ЧУЖОЕ, и через неделю вопрос будет
    ровно один: почему вчерашний фильм не открылся с диска. Ответ обязан лежать полями.
    """
    from torrcast.usecases.warm.settings import META
    from torrcast.usecases.warm.vault import Vault

    root = tmp_path / "warm"
    old = Vault(root=root, key="старый", budget=1000, floor=0, title="Тачки 3")
    old.open()
    old.path(0).write_bytes(b"x" * 400)
    os.utime(old.dir / META, (time.time() - 86400, time.time() - 86400))
    mine = Vault(root=root, key="мой", budget=1000, floor=0)
    mine.open()
    mine.path(0).write_bytes(b"x" * 400)

    assert mine.fit(300) == "", "место обязано найтись за счёт чужого"
    shutdown()

    rec = _only(_read_lines(tmp_path), "evict")
    assert rec["phase"] == "warm"
    assert rec["key"] == "старый"
    assert rec["title"] == "Тачки 3"
    assert rec["freed"] == 400
    assert rec["need"] == 300
    assert "вытеснил «Тачки 3»" in digest(records())


def test_a_piece_laid_off_the_grid_is_a_record_with_numbers(tmp_path: Path) -> None:
    """Промах укладки мимо сетки - поля, а не строка: где, на сколько, чем кончилось.

    Дефект укладки мимо сетки прожил незамеченным неделями
    (:meth:`torrcast.usecases.warm.Warmer._verify`),
    и вопрос через неделю будет ровно один: срабатывал ли сторож и на каких местах. Ответ
    обязан лежать числами - границей, фактическим началом и разницей между ними, - а не
    печататься в журнал показа, который гаснет вместе с ним.
    """
    skew(slot=7, want=88.0, got=86.29, hole=True)
    shutdown()

    rec = _only(_read_lines(tmp_path), "skew")
    assert rec["phase"] == "warm"
    assert rec["slot"] == 7
    assert rec["want"] == 88.0
    assert rec["got"] == 86.29
    assert rec["off"] == -1.71, "разница обязана лежать полем, а не считаться читателем"
    assert rec["hole"] is True
    assert rec["src"] == WARMED, "источник куска назван не так, как в записи отдачи"
    text = digest(records())
    assert "v7 лёг мимо сетки" in text and "место осталось непрогретым" in text
    assert "кусков мимо сетки 1" in text


def test_the_share_of_the_warmed_movie_is_a_field(tmp_path: Path) -> None:
    """Доля прогретого уходит в ленту числами, а не строкой «прогрето 42 мин из 96».

    Строка остаётся человеку в живом показе; недельному разбору нужны секунды, длина
    фильма, доля и вес каталога - по ним видно, докуда дошёл прогрев и почему встал.
    """
    from torrcast.adapters.stream_pack.grid import Grid
    from torrcast.usecases.warm.vault import Vault
    from torrcast.usecases.warm.warmer import Warmer

    grid = Grid.uniform(100.0)
    vault = Vault(root=tmp_path / "warm", key="k", budget=1 << 30, floor=0)
    vault.open()
    for slot in range(3):
        vault.path(slot).write_bytes(b"x" * 1024)
    warmer = Warmer(source="clip", audio=0, grid=grid, vault=vault, log=lambda _line: None)
    warmer._stall("бюджет диска 20 ГБ исчерпан")
    shutdown()

    rec = _only(_read_lines(tmp_path), "stall")
    assert rec["phase"] == "warm"
    assert rec["dur"] == 100
    assert rec["secs"] == round(warmer.warmed)
    assert rec["share"] == round(warmer.warmed / 100.0, 3)
    assert rec["size"] == 3 * 1024
    assert rec["why"] == "бюджет диска 20 ГБ исчерпан"
    assert "прогрев встал: бюджет диска 20 ГБ исчерпан" in digest(records())


def test_the_new_fields_never_break_an_old_journal(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Лента, записанная ДО этих полей, обязана читаться `cast log` как читалась.

    Разбор старых записей - не украшение: недельный след затем и держат неделю, чтобы
    вчерашний сеанс пережил сегодняшнее обновление. Здесь - запись ровно того формата,
    который был до добора полей, плюс событие, о котором эта версия не знает вовсе.
    """

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

    assert main(["log"]) == 0
    text = capsys.readouterr().out
    assert "матрица" in text
    assert "ребуфер на 2:00" in text
    assert "ребуферов 1" in text and "нуджей" not in text
    assert "остановлено на 1:30:00" in text


def test_cast_log_shows_the_new_events(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Сквозная проверка: события легли в ленту - и `cast log` их напечатал."""

    emit("search", "query", query="тачки")
    nudge(pos=84.0, to=92.0, hit=1, stuck=9.0, front=144.0)
    seek(frm=600.0, to=1891.0, wait=3.2)
    evict(key="k", freed=4_200_000_000, need=1_000_000_000, title="Тачки 3")
    warmth("ready", secs=2520.0, dur=5760.0, size=6_000_000_000)
    shutdown()

    assert main(["log"]) == 0
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

    emit("search", "query", query="матрица")
    shutdown()
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
    monkey.setenv(LOG_ENV, str(tmp_path))
    monkey.setenv(SID_ENV, "src")
    segment(slot=40, mb=3.1, sent=0.4, wait=0.02, src=PACKED)
    segment(slot=41, mb=2.9, sent=0.3, wait=0.01, src=WARMED)
    shutdown()
    rows = [r for r in records() if r.get("event") == "segment"]
    monkey.undo()

    assert [r["src"] for r in rows] == ["pack", "warm"], "источник куска в ленту не попал"
    assert rows[0]["slot"] == 40 and rows[0]["mb"] == 3.1, "прежние поля записи потерялись"
    seams = _seams(rows)
    assert [r["slot"] for r in seams] == [41], "смена производителя посреди показа не видна"
    assert "стыков источника 1" in digest(rows), "выжимка молчит про стык источников"
    assert "источник сменился на прогретое" in digest(rows), "стык не назван"


def test_the_plan_says_how_both_producers_encode(tmp_path: Path) -> None:
    """Решение о кодировании - строка ленты, а не разбор аргументов ffmpeg постфактум."""
    monkey = pytest.MonkeyPatch()
    monkey.setenv(LOG_ENV, str(tmp_path))
    monkey.setenv(SID_ENV, "plan")
    plan(pack="copy", warm="copy", spots=5, preset="veryfast", mbit=9.0)
    shutdown()
    rows = [r for r in records() if r.get("event") == "plan"]
    monkey.undo()

    assert rows[0]["pack"] == "copy" and rows[0]["warm"] == "copy", "решения в ленте нет"
    assert rows[0]["spots"] == 5, "точечный перекод не сосчитан"
    assert "упаковка - копия, прогрев - копия" in digest(rows), "выжимка молчит о решении"


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
    from torrcast.adapters.filesystem.stopwatch import mark

    emit("search", "query", query="сталкер", raw=41, pictures=3)
    mark("отбор релиза", релиз=2)
    mark("упаковка пошла")
    mark("упаковка пошла")  # фаза повторяется: у показа их бывают десятки
    emit("session", "session_end", pos=60.0, dur=120.0, watched=False)
    shutdown()

    assert main(["log"]) == 0
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

    emit("play", "нечто", чего_мы_не_знаем=1)
    shutdown()

    assert main(["log"]) == 0
    assert "play/нечто (чего_мы_не_знаем=1)" in capsys.readouterr().out
