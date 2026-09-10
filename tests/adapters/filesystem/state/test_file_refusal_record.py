"""Файловая запись отказа: слово переживает процесс писателя, а битый файл молчит."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.file_refusal_record import FileRefusalRecord


@pytest.fixture
def own_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Своё состояние на пробу: запись обязана лечь рядом с ним, а не с чужим."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    yield tmp_path


def test_the_word_survives_the_writing_process(own_state: Path) -> None:
    """Юнит умирает сразу после записи - читает её уже мост, другим процессом.

    Мост и юнит не делят память; «другим процессом» тут честно занимает другой
    экземпляр держателя, собранный заново, как это делает свой процесс моста.
    """
    FileRefusalRecord().record("receiver_did_not_answer")

    assert FileRefusalRecord().read() == "receiver_did_not_answer"


def test_an_empty_word_is_not_written_at_all(own_state: Path) -> None:
    """Пустое слово - граница способа, а не запись: файла за ним быть не должно."""
    FileRefusalRecord().record("")

    assert not (own_state / "start-refusal.json").exists()


def test_a_broken_record_reads_as_no_word(own_state: Path) -> None:
    """Файл правили руками и сломали - читатель отвечает «причины не знаем»."""
    (own_state / "start-refusal.json").write_text("это не json", encoding="utf-8")

    assert FileRefusalRecord().read() is None


def test_forgetting_erases_the_record_of_the_previous_raise(own_state: Path) -> None:
    """Новый подъём взят в работу - слово ПРОШЛОГО отказа ему не принадлежит."""
    record = FileRefusalRecord()
    record.record("source_did_not_answer")

    record.forget()

    assert record.read() is None


def test_a_shut_disk_does_not_crash_the_dying_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запись - последняя правда умирающего показа, и ради неё самой он не падает."""
    busy = tmp_path / "занято"
    busy.write_text("файл, а не каталог", encoding="utf-8")
    monkeypatch.setenv("TORRCAST_STATE", str(busy / "state.json"))
    record = FileRefusalRecord()

    record.record("receiver_did_not_answer")
    record.forget()

    assert record.read() is None
