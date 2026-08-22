"""Подъём работы в стороне: заказчик возвращается сразу, а работа всё равно идёт."""

from __future__ import annotations

import threading

import pytest

from torrcast.adapters.side_thread import side_thread


@pytest.mark.machine
def test_the_caller_comes_back_before_the_work_is_done() -> None:
    """Ради этого слот и заведён: у зовущего своё расписание, и ждать ему нельзя."""
    let_go = threading.Event()
    done = threading.Event()

    def work() -> None:
        let_go.wait(1.0)
        done.set()

    side_thread(work)

    assert not done.is_set(), "заказчик вернулся только вместе с работой"
    let_go.set()
    assert done.wait(1.0), "работа так и не пошла"


@pytest.mark.machine
def test_the_work_does_not_hold_the_process_after_the_show() -> None:
    """Демон: работа подсобная, и держать ею процесс, когда показ окончен, незачем."""
    seen: list[bool] = []
    started = threading.Event()

    def look() -> None:
        seen.append(threading.current_thread().daemon)
        started.set()

    side_thread(look)

    assert started.wait(1.0) and seen == [True]
