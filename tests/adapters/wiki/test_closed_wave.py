"""Проверяет волну ниток, закрытую за собой: срок решает ответ, закрытие платит поднявший."""

import threading
import time

from tests import thread_guard
from torrcast.adapters.wiki.closed_wave import closed_wave


def test_the_answer_is_taken_by_the_deadline_and_the_wave_is_closed_after_it() -> None:
    """🔴 TC-723. Ответ снимается ПО СРОКУ, а нитка закрывается тем, кто её поднял.

    Две вещи разом, и обе нужны. Ответ по сроку: опоздавшая нитка не вправе задним числом
    поменять то, что спрашивающему уже объявлено. Закрытие после: брошенная нитка доживает
    своё в чужой работе - в бою это показ, в прогоне соседняя проба, и красным там будет
    невиновный.
    """
    box: list[str] = []
    done: list[float] = []
    late = threading.Event()

    def slow() -> None:
        late.wait(1.0)  # нитка отвечает, но много позже отведённого срока
        box.append("опоздавший")
        done.append(time.monotonic())

    wave = [threading.Thread(target=slow, daemon=True, name="проба-волны")]
    before = thread_guard.alive()
    wave[0].start()

    answer = closed_wave(wave, time.monotonic() + 0.05, lambda: list(box))

    assert answer == [], "по сроку не приехало ничего - это и есть ответ"
    assert box == ["опоздавший"], "опоздавшая нитка доработала, а не была брошена"
    left = thread_guard.alive() - before
    assert not left, f"нитку закрыл тот, кто её поднял, а живой осталась {left}"
    # Рубеж - момент, когда нитка доработала, а не длительность её ожидания:
    # Event.wait вправе отпустить чуть раньше срока, его таймаут и time.monotonic
    # считаются по разным часам.
    assert done and time.monotonic() >= done[0], "ответ отдан после закрытия, а не вместо него"


def test_the_wave_is_waited_out_as_a_wave_not_as_a_queue() -> None:
    """Срок один на всю волну: очередь из сроков сдвигает момент, когда снят ответ.

    Ждали волну прежде очередью, по своему сроку каждой нитке, - и ответ снимался тем
    позже, чем больше ниток отвечало до него. Внутрь потолка справки такая очередь не
    влезает по построению: шаг из трёх запросов возвращался втрое позже обещанного.
    """
    box: list[str] = []

    def answering(after: float, mark: str) -> None:
        time.sleep(after)
        box.append(mark)

    wave = [
        threading.Thread(target=answering, args=(0.3, "в срок"), daemon=True, name="проба-1"),
        threading.Thread(target=answering, args=(0.3, "в срок"), daemon=True, name="проба-2"),
        threading.Thread(target=answering, args=(0.6, "опоздал"), daemon=True, name="проба-3"),
    ]
    before = thread_guard.alive()
    for thread in wave:
        thread.start()

    answer = closed_wave(wave, time.monotonic() + 0.4, lambda: list(box))

    assert answer == ["в срок", "в срок"], f"ответ снят не по сроку волны: {answer}"
    assert not thread_guard.alive() - before, "волну закрыл тот, кто её поднял"
