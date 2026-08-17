"""Рассказ о перешагнутой плёнке: сказать можно только там, где пропуск известен числом."""

from __future__ import annotations

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from torrcast.adapters.chromecast.cast.say_skip import _say_skip


def test_the_viewer_is_told_how_much_film_the_watchdog_cost_him(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Прыжок сторожа - размен, и цена его в секундах фильма называется вслух.

    Замер на живом Q70D: показ встал на 103.6 с, прыжок ушёл на 119.2 с - 15.6 с мимо,
    и об этом не было сказано ни строки. Человек у экрана слышит пропавший звук и
    гадает, файл это или техника.
    """
    receiver = Wired()
    receiver._skip_from = 103.6

    _say_skip(receiver, 119.2)

    said = capsys.readouterr().out
    assert "приёмник зависал" in said
    assert "16 с фильма" in said
    assert "104 с -> 119 с" in said
    assert receiver._skip_from == -1.0, "о том же пропуске вторым голосом не говорим"


def test_a_show_that_never_jumped_says_nothing(capsys: pytest.CaptureFixture[str]) -> None:
    """Никуда не прыгали - и рассказывать не о чем."""
    receiver = Wired()

    _say_skip(receiver, 500.0)

    assert capsys.readouterr().out == ""


def test_a_skip_smaller_than_the_measurement_step_is_not_named(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Опрос идёт раз в 2 с, и всё, что мельче, - разрешение замера, а не потерянная плёнка."""
    receiver = Wired()
    receiver._skip_from = 100.0

    _say_skip(receiver, 100.0 + receiver.SKIP_FLOOR - 0.1)

    assert capsys.readouterr().out == ""
    assert receiver._skip_from == -1.0, "счёт всё равно снят: прыжка больше нет"
