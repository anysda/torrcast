"""Проверяет нитки, поднятые по ключу: одна на ключ, и опоздавший ответ не пропадает."""

import threading
import time

from tests import thread_guard
from torrcast.usecases.lookers import Lookers


def test_one_key_is_one_thread_no_matter_how_many_ask() -> None:
    """🔴 TC-723. Сто спросов про одно имя - одна нитка, а не сто.

    Оборвать нитку, залипшую в системном вызове, в Python нечем: срок отпускает
    спрашивающего, а нитка живёт дальше. Там, где по сроку отвечают человеку, платить её
    закрытие некому - потолок ожидания справки продуктовый. Поэтому мерой тут становится
    ЧИСЛО ниток, и лечится оно ключом: пока нитка заводилась на каждый спрос, молчащий
    источник стоил по нитке за спрос, и все они доживали своё уже в показе.
    """
    holding = threading.Event()
    asked = 0

    def slow() -> str:
        nonlocal asked
        asked += 1
        holding.wait(2.0)
        return "приехало"

    lookers: Lookers[str] = Lookers()
    before = thread_guard.alive()
    try:
        for _ in range(100):
            assert lookers.ask("одно имя", slow, 0.0) is None, "по нулевому сроку ответа нет"
        raised = thread_guard.alive() - before
        assert len(raised) == 1, f"нитка одна на ключ, а поднято {len(raised)}"
        assert asked == 1, f"источник спрошен один раз, а спрошен {asked}"
    finally:
        holding.set()
    lookers.ask("одно имя", slow, 2.0)  # дожидаемся своей нитки: её подняли мы

    assert not thread_guard.alive() - before


def test_an_answer_that_missed_its_deadline_is_free_for_the_next_asker() -> None:
    """Опоздавший ответ пишет сама нитка - следующему он достаётся даром, а не заново."""
    late = threading.Event()

    def slow() -> str:
        late.wait(0.4)  # источник отвечает, но много позже первого срока
        return "приехало"

    lookers: Lookers[str] = Lookers()
    before = thread_guard.alive()

    assert lookers.ask("имя", slow, 0.05) is None, "в свой срок ответ не приехал"
    assert lookers.ask("имя", slow, 1.0) == "приехало", "опоздавший ответ не пропал"

    started = time.monotonic()
    assert lookers.ask("имя", slow, 1.0) == "приехало"
    assert time.monotonic() - started < 0.1, "готовый ответ отдаётся из памяти, а не заново"
    assert not thread_guard.alive() - before


def test_silence_is_not_remembered_and_may_be_asked_again() -> None:
    """Пустой ответ - это не «ничего нет»: переспросить его следующему никто не мешает."""
    asked = 0

    def silent() -> str:
        nonlocal asked
        asked += 1
        return ""

    lookers: Lookers[str] = Lookers()
    assert lookers.ask("имя", silent, 1.0) is None
    assert lookers.ask("имя", silent, 1.0) is None
    assert asked == 2, "молчание источника в память не ложится"
