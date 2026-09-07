"""Зеркало взятия показа: новый показ снимает идущий, а не отказывает ему (ТЗ §7.4)."""

from __future__ import annotations

import threading
import time
from collections.abc import Sequence

import pytest

from hass.orders import Orders
from hass.starting import starting
from tests.fakes.playback_session import FakePlaybackSession

#: Сколько ждать движения чужого потока, прежде чем считать, что его не будет.
PATIENCE = 5.0


class _Show:
    """Показ, который висит, пока его не снимут: так ведёт себя настоящий подъём.

    Настоящая команда читает отказ на своих поворотах
    (:func:`torrcast.ports.abandon.slot.abandoned`) и уходит с них; тут поворот один, и
    того довольно: зеркало меряет не подъём, а очередь под ним.
    """

    def __init__(self) -> None:
        self.taken: list[list[str]] = []
        self.orders: Orders | None = None

    def __call__(self, argv: Sequence[str] | None) -> int:
        args = list(argv or [])
        self.taken.append(args)
        if args == ["stop"]:
            return 0
        assert self.orders is not None
        began = time.monotonic()
        while not self.orders.abandoned() and time.monotonic() - began < PATIENCE:
            time.sleep(0.01)
        return 0

    def waited(self, count: int) -> bool:
        """Дождаться, пока поручений исполнено не меньше ``count``."""
        began = time.monotonic()
        while len(self.taken) < count and time.monotonic() - began < PATIENCE:
            time.sleep(0.01)
        return len(self.taken) >= count


def _running(orders: Orders) -> threading.Thread:
    """Поток, изображающий главный: настоящий зовёт то же самое (:func:`hass.main.main`)."""
    thread = threading.Thread(target=orders.run, daemon=True)
    thread.start()
    return thread


def test_a_show_asked_on_an_empty_queue_is_taken_without_stopping_anything() -> None:
    """Никто не играет - снимать нечего, и трогать сеанс не за что."""
    session = FakePlaybackSession()
    show = _Show()
    orders = Orders(show)
    show.orders = orders

    assert starting(orders, session, ["матрица"])

    assert session.stopped == 0, "показа не было, а сеанс погасили"


@pytest.mark.machine
def test_a_second_show_takes_the_queue_from_the_first_instead_of_being_refused() -> None:
    """🔴 ТЗ §7.4: «Играть» поверх идущего показа СНИМАЕТ его.

    Отказ ``busy`` на этом месте делал кнопку немой: страница жала «Играть», получала 409
    и не меняла ни строки. Порядок поручений тут - сам приговор: остановка обязана уйти
    из очереди ДО того, как в неё встал новый показ, иначе она снимет уже его.
    """
    session = FakePlaybackSession(playing=True)
    show = _Show()
    orders = Orders(show)
    show.orders = orders
    thread = _running(orders)
    try:
        assert orders.take(["матрица"])
        assert show.waited(1), "первый показ так и не поехал"

        assert starting(orders, session, ["муха"]), "второму показу отказали очередью"
        assert show.waited(3), "поручений исполнено меньше трёх"
    finally:
        orders.abandon()  # новый показ висит на своём повороте, пока его не снимут
        orders.leave()
        thread.join(timeout=PATIENCE)

    assert show.taken == [["матрица"], ["stop"], ["муха"]]
    assert session.stopped == 1, "идущий показ не погасили"


@pytest.mark.machine
def test_the_new_show_starts_without_the_abandonment_meant_for_the_old_one() -> None:
    """🔴 Снятие относилось к ПРОШЛОМУ показу, и новый обязан поехать без него.

    Взять поручение раньше, чем остановка ушла из очереди, значило бы встать ЗА ней: она
    сняла бы защёлку подъёма в своём ``finally`` уже с нового показа, и мост считал бы
    себя свободным при идущем показе.
    """
    session = FakePlaybackSession(playing=True)
    show = _Show()
    orders = Orders(show)
    show.orders = orders
    thread = _running(orders)
    try:
        assert orders.take(["матрица"])
        assert show.waited(1)

        assert starting(orders, session, ["муха"])
        assert show.waited(3)

        assert orders.underway(), "новый показ идёт, а мост считает себя свободным"
        assert not orders.abandoned(), "новый показ поехал уже снятым"
    finally:
        orders.abandon()
        orders.leave()
        thread.join(timeout=PATIENCE)
