"""Фоновый писатель: укладка в очередь без диска, конечная очередь и дожатие хвоста."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal import writer as writer_module
from torrcast.adapters.filesystem.trace_journal.writer import (
    _BATCH,
    _QUEUE_MAX,
    _Writer,
    _writer,
)


def test_putting_a_record_touches_the_queue_and_never_the_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Главный инвариант ленты: укладка записи не делает ни одного обращения к диску.

    :meth:`put` зовут из горячего пути отдачи сегмента. Сделай он тут ``open`` или
    ``write`` - и показ ждал бы диск на каждом куске.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    monkeypatch.setattr(_Writer, "_start", lambda self: None)  # поток не поднимаем
    touched: list[str] = []

    def opened(*_a: object, **_k: object) -> int:
        touched.append("open")
        return 3

    def written(*_a: object, **_k: object) -> int:
        touched.append("write")
        return 0

    monkeypatch.setattr(os, "open", opened)
    monkeypatch.setattr(os, "write", written)

    writer = _Writer()
    for slot in range(50):
        writer.put({"phase": "play", "event": "segment", "slot": slot})

    assert touched == []
    assert writer._q.qsize() == 50, "запись лежит в очереди, а не на диске"


def test_the_tape_file_is_chosen_at_the_moment_of_the_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Файл выбирается при укладке и едет в очереди вместе с записью.

    Выбирай его писатель у себя, отставший хвост уезжал бы в ленту, на которую окружение
    показывает СЕЙЧАС, - то есть в чужую.
    """
    monkeypatch.setattr(_Writer, "_start", lambda self: None)
    writer = _Writer()

    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path / "первая"))
    writer.put({"event": "первая"})
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path / "вторая"))
    writer.put({"event": "вторая"})

    queued = [writer._q.get_nowait(), writer._q.get_nowait()]
    assert [item[0].parent.name for item in queued if item] == ["первая", "вторая"]


def test_a_full_queue_drops_the_record_and_counts_the_loss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Очередь конечна: переполнение роняет запись, но показ не ждёт ни мгновения.

    Молчать об этом нельзя - потери считаются, и признание уходит в ленту отдельной
    записью; здесь проверяется сам счёт.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    monkeypatch.setattr(writer_module, "_QUEUE_MAX", 2)
    monkeypatch.setattr(_Writer, "_start", lambda self: None)

    writer = _Writer()
    for slot in range(10):
        writer.put({"phase": "play", "event": "segment", "slot": slot})

    assert writer._q.qsize() == 2
    assert writer._lost == 8


def test_stopping_a_writer_without_a_thread_still_presses_the_tail_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Поток не поднимался - :meth:`stop` дожимает хвост синхронно, а не теряет его."""
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    monkeypatch.setattr(_Writer, "_start", lambda self: None)

    writer = _Writer()
    writer.put({"phase": "play", "event": "segment", "slot": 1})
    writer.stop()

    assert [path.name for path in tmp_path.glob("trace-*.jsonl")], "хвост не записался"


def test_the_queue_is_deep_enough_for_a_show_and_there_is_one_writer_per_process() -> None:
    """Глубина очереди - тысячи записей, а писатель на процесс ровно один.

    Второй писатель означал бы вторую очередь и второй фоновый поток на тот же файл, то
    есть перемешанные пакеты и удвоенную ротацию.
    """
    assert _QUEUE_MAX == 4096
    assert _BATCH == 256
    assert _BATCH < _QUEUE_MAX, "пакет обязан быть мельче очереди, иначе он её и есть"
    assert isinstance(_writer, _Writer)


def test_the_writer_confesses_its_losses_once_and_keeps_the_rotation_mark(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Счётчик потерь обнуляется признанием, а метка ротации живёт у писателя.

    Не обнули счётчик - и одна потеря признавалась бы в каждом следующем пакете;
    не запомни метку - ротация шла бы на каждый пакет, то есть в фоне показа.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    monkeypatch.setattr(_Writer, "_start", lambda self: None)
    writer = _Writer()
    writer.put({"phase": "play", "event": "segment", "slot": 1})
    writer._lost = 4

    writer.stop()  # thread не поднимался - stop дожимает синхронно через drain

    assert writer._lost == 0
    assert writer._pruned, "метка ротации осталась у писателя, а не сгорела в вызове"
    tape = next(iter(tmp_path.glob("trace-*.jsonl")))
    assert '"lost"' in tape.read_text("utf-8")


@pytest.mark.machine
def test_the_background_thread_is_raised_by_the_very_first_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Поток поднимается лениво - на первой записи, и ровно один раз на писателя.

    Подними его конструктор - каждый импорт пакета заводил бы демона на пустом месте;
    не подними вовсе - лента копилась бы в очереди и уходила только по явному дожатию.
    """
    monkeypatch.setenv("TORRCAST_LOG", str(tmp_path))
    started: list[str] = []

    def raise_it(writer: _Writer) -> None:
        started.append("вверх")
        # Как настоящий подъём: поток заводится, но не стартует - живой демон тут не нужен.
        writer._thread = threading.Thread(target=lambda: None)

    monkeypatch.setattr(_Writer, "_start", raise_it)

    writer = _Writer()
    assert started == [], "до первой записи поднимать нечего"

    writer.put({"phase": "play", "event": "segment", "slot": 1})
    writer.put({"phase": "play", "event": "segment", "slot": 2})

    assert started == ["вверх"], "поток один на писателя, а не один на запись"
