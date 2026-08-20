"""Сторож утёкших потоков (:mod:`tests.thread_guard`): кого он называет и кого прощает."""

from __future__ import annotations

import threading

import pytest

from tests import thread_guard
from torrcast.adapters.filesystem.trace_journal import writer


def _held(name: str) -> tuple[threading.Thread, threading.Event]:
    """Поток, который живёт до отмашки: так изображается и утёкший, и закрытый."""
    hold = threading.Event()
    worker = threading.Thread(target=hold.wait, args=(30.0,), name=name)
    worker.start()
    return worker, hold


@pytest.mark.machine
def test_a_thread_that_outlived_the_probe_is_named() -> None:
    """Живой после пробы поток назван поимённо - иначе искать виновника негде."""
    before = thread_guard.alive()
    worker, hold = _held("утёкший")
    try:
        left = thread_guard.leaked(before)
        assert [thread.name for thread in left] == ["утёкший"]
        assert "утёкший" in thread_guard.complain("проба::тест", left)
    finally:
        hold.set()
        worker.join(timeout=5.0)


@pytest.mark.machine
def test_a_thread_closed_behind_is_not_named() -> None:
    """Закрытый за собой поток сторожу не в укор, и ждать его сторож не заставляет."""
    before = thread_guard.alive()
    worker, hold = _held("закрытый")
    hold.set()
    worker.join(timeout=5.0)

    assert thread_guard.leaked(before) == []


@pytest.mark.machine
def test_the_tape_writer_of_the_whole_process_is_forgiven(monkeypatch: pytest.MonkeyPatch) -> None:
    """Фоновая запись ленты принадлежит процессу, а не пробе: её сторож не вменяет никому."""
    before = thread_guard.alive()
    worker, hold = _held("torrcast-trace")
    try:
        monkeypatch.setattr(writer._writer, "_thread", worker)
        assert thread_guard.leaked(before) == []
    finally:
        hold.set()
        worker.join(timeout=5.0)
