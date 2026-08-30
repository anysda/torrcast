"""Счёт смертей по кускам: место подъёма уезжает ЗА кусок, который убивает показ."""

from __future__ import annotations

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from torrcast.adapters.chromecast.cast.past_deadly import _past_deadly

#: Сетка неровными кусками, как её и режет ffmpeg по опорным кадрам.
_CUTS = (124.583, 137.095, 144.0, 152.0)


def _cut(at: float) -> float:
    """Конец куска, накрывающего эту секунду фильма."""
    return next((edge for edge in _CUTS if edge > at), _CUTS[-1])


def test_without_a_grid_there_is_nowhere_to_step_and_nothing_to_count() -> None:
    """Границ не назвали - прыгать на глазок значит промахнуться, только тише."""
    receiver = Wired()

    assert _past_deadly(receiver, 125.4) == 125.4
    assert receiver._deaths == {}


def test_the_first_deaths_return_the_viewer_where_he_was_watching() -> None:
    """Моргнувшая сеть тоже гасит показ: первая смерть о куске ещё ничего не говорит."""
    receiver = Wired()
    receiver.next_cut = _cut

    assert _past_deadly(receiver, 125.4) == 125.4
    assert _past_deadly(receiver, 125.4) == 125.4


def test_a_segment_that_keeps_killing_the_show_is_stepped_over(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Набралось - кусок невоспроизводим, и возвращаться в него значит идти за смертью.

    Замер на «Моане» 2016: приёмник умирал на одном месте четыре раза, и каждый круг
    восстановления отдавал ему тот же кусок. За 5 мин 48 с позиция сдвинулась со
    125.4 на 127.8 с, показ кончился непросмотренным.
    """
    receiver = Wired()
    receiver.next_cut = _cut

    for _ in range(receiver.DEADLY_TRIES - 1):
        _past_deadly(receiver, 125.4)
    to = _past_deadly(receiver, 125.4)

    assert to == _cut(125.4 + receiver.profile.start_buffer) + receiver.CUT_SLACK
    assert to > 125.4
    assert "skipping it" in capsys.readouterr().out


def test_deaths_are_counted_where_the_show_died_and_not_where_the_jump_aims() -> None:
    """Кусков два: считаем по месту смерти, а прыгаем за тот, где давится декодер.

    Считай мы по цели - ``at`` подрастает, ключ рвёт границу сетки не там, и смерти
    разъезжаются по двум счётчикам: перешагивание опоздает на круг восстановления.
    """
    receiver = Wired()
    receiver.next_cut = _cut
    drift = (125.4, 127.2, 127.8)
    assert len({_cut(at) for at in drift}) == 1, "замер: дрейф не выходит из куска"
    assert len({_cut(at + receiver.profile.start_buffer) for at in drift}) == 2, (
        "и ровно на этом дрейфе прицел меняет кусок - иначе тест ничего не сторожит"
    )

    steps = [_past_deadly(receiver, at) for at in drift]

    assert steps[-1] > drift[-1], "третья смерть на том же куске уже перешагивается"
    assert len(receiver._deaths) == 1, "смерти сложились в один счётчик, а не в два"
