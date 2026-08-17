"""Зеркало :mod:`torrcast.domain.first_frame_ready`."""

from __future__ import annotations

from torrcast.domain.first_frame_ready import first_frame_ready

#: Столько фильма приёмник копит до первого кадра - замер осторожного профиля.
BUFFER = 10.0


def test_the_receiver_gathers_the_measured_buffer_before_the_first_frame() -> None:
    """Восьми секунд впереди приёмнику мало, шестнадцати - хватает."""
    assert not first_frame_ready(False, 300.0, 308.0, BUFFER)
    assert first_frame_ready(False, 300.0, 316.0, BUFFER)


def test_the_receiver_gathers_once_and_never_again() -> None:
    """Кадр уже был на экране - копит приёмник один раз, на заходе."""
    assert first_frame_ready(True, 300.0, 303.0, BUFFER)


def test_nothing_named_ahead_means_nothing_to_judge() -> None:
    """Запас показу известен не всегда, и в этом случае работает прежнее правило."""
    assert first_frame_ready(False, 300.0, 0.0, BUFFER)
    assert first_frame_ready(False, 300.0, 300.0, BUFFER)
