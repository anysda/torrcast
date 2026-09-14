"""Проверяет приоритет клика над ещё не начавшимся фоном Wikimedia."""

import threading
import time

import pytest

from torrcast.adapters.wiki.request_lanes import RequestLanes


@pytest.mark.machine
def test_a_card_gets_the_next_lane_before_a_waiting_background_wave() -> None:
    """Завершившийся фон выпускает первым клик, а не следующий пакет прогрева."""
    lanes = RequestLanes()
    assert all(lanes.acquire(0.1, foreground=False) for _ in range(5))
    started = threading.Event()
    card_started = threading.Event()
    finished: list[str] = []

    def background() -> None:
        started.set()
        assert lanes.acquire(1.0, foreground=False)
        finished.append("background")
        lanes.release()

    def card() -> None:
        card_started.set()
        assert lanes.acquire(1.0, foreground=True)
        finished.append("card")
        lanes.release()

    behind = threading.Thread(target=background)
    behind.start()
    assert started.wait(1.0)
    time.sleep(0.02)
    urgent = threading.Thread(target=card)
    urgent.start()
    assert card_started.wait(1.0)
    time.sleep(0.02)
    lanes.release()
    urgent.join(1.0)
    behind.join(1.0)
    for _ in range(4):
        lanes.release()
    assert finished == ["card", "background"]
