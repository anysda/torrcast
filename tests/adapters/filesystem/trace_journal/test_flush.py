"""Пакет на диск: признание в потерях, разные ленты в одном пакете, дозапись строками."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from torrcast.adapters.filesystem.trace_journal.flush import _flush


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _today(directory: Path) -> Path:
    """Лента сегодняшних суток: старую ротация снесла бы прямо в этом же вызове."""
    return directory / f"trace-{time.strftime('%Y%m%d')}.jsonl"


def test_records_of_one_batch_land_as_whole_lines_in_their_own_file(tmp_path: Path) -> None:
    """Одна запись - одна строка JSON, и дозапись идёт в конец, ничего не затирая."""
    tape = _today(tmp_path)

    marked = _flush([(tape, {"event": "первая"}), (tape, {"event": "вторая"})], 0, "")
    _flush([(tape, {"event": "третья"})], 0, marked)

    assert [row["event"] for row in _rows(tape)] == ["первая", "вторая", "третья"]


def test_a_batch_that_spans_two_tapes_splits_by_the_file_each_record_chose(
    tmp_path: Path,
) -> None:
    """Каталог ленты сменился на ходу - каждая запись едет туда, куда собиралась.

    Обычно файл у пакета один. Разные файлы в одном пакете - это ровно тот случай, ради
    которого путь и едет в очереди рядом с записью.
    """
    first, second = _today(tmp_path / "а"), _today(tmp_path / "б")

    _flush([(first, {"event": "своя"}), (second, {"event": "чужая"})], 0, "")

    assert [row["event"] for row in _rows(first)] == ["своя"]
    assert [row["event"] for row in _rows(second)] == ["чужая"]


def test_the_loss_is_confessed_in_the_tape_next_to_the_records_that_survived(
    tmp_path: Path,
) -> None:
    """Переполнение очереди признаётся записью ``lost`` перед первой записью пакета.

    Без признания разбор недели уверенно прочитает пропуск как «событий не было», а это
    худшее, что лента может сказать о показе.
    """
    tape = _today(tmp_path)

    _flush([(tape, {"event": "segment"})], 3, "")

    rows = _rows(tape)
    assert [row["event"] for row in rows] == ["lost", "segment"]
    assert rows[0]["count"] == 3
    assert rows[0]["phase"] == "trace"
    # Конверт у признания свой, собранный здесь: разойдись он с конвертом обычной
    # записи - разбор недели не нашёл бы признание в ленте своего же сеанса.
    assert set(rows[0]) >= {"at", "sid", "pid", "phase", "event", "count"}


def test_a_confession_without_survivors_still_reaches_the_tape(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пустой пакет с потерями - тоже пакет: он ложится в ленту сегодняшних суток.

    Своего файла у признания нет - потерянные записи в очередь не попали, - поэтому
    место ему выбирается тут же, а не пропускается вместе с пустым хвостом.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))

    _flush([], 5, "")

    written = sorted(tmp_path.glob("trace-*.jsonl"))
    assert len(written) == 1
    assert [row["event"] for row in _rows(written[0])] == ["lost"]


def test_a_directory_that_cannot_be_written_does_not_bring_the_show_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Диск отказал - лента молчит, а показ идёт: диагностика не роняет картинку."""
    tape = _today(tmp_path)

    def refuse(*_a: object, **_k: object) -> int:
        raise OSError("диск недоступен")

    monkeypatch.setattr("os.open", refuse)

    _flush([(tape, {"event": "segment"})], 0, "")

    assert not tape.exists()
