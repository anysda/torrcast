"""Зеркало :mod:`torrcast.domain.frames.mkv.window`: окно у индекса одним заходом к рою."""

from __future__ import annotations

from tests.domain.frames.mp4.boxes import Served
from torrcast.domain.frames.mkv.window import BEFORE, Window

DATA = bytes(range(256)) * ((BEFORE + (3 << 20)) // 256)


def test_the_window_takes_the_bytes_before_the_index_in_the_same_request() -> None:
    """Индекс и кластеры перед ним - один заход: рой платит за место, а не за мегабайт."""
    served = Served(DATA)
    at = BEFORE + (1 << 20)
    near = Window(served, at, 4096)

    assert served.asked == [(at - BEFORE, BEFORE + 4096)]
    assert near.tail(at) == DATA[at : at + 4096]
    assert near.read(at - 1000, 500) == DATA[at - 1000 : at - 500]
    assert served.requests == 1, "проба внутри окна отвечает из памяти"


def test_a_read_outside_the_window_goes_to_the_swarm() -> None:
    """Проба в голове ленты окну не принадлежит - за ней честный заход к рою."""
    served = Served(DATA)
    at = BEFORE + (1 << 20)
    near = Window(served, at, 4096)

    assert near.read(16, 32) == DATA[16:48]
    assert near.read(at + 4000, 200) == DATA[at + 4000 : at + 4200], "через край окна - в рой"
    assert served.requests == 3
    assert (near.taken, near.requests) == (served.taken, served.requests)


def test_a_window_cut_by_the_end_of_the_file_answers_past_its_edge() -> None:
    """Индекс в конце файла: окно упёрлось в конец, и дальше читать в рою нечего."""
    served = Served(DATA)
    at = len(DATA) - 100
    near = Window(served, at, 1 << 20)

    assert near.read(at + 50, 4096) == DATA[at + 50 :]
    assert served.requests == 1


def test_an_index_in_the_head_starts_the_window_at_the_file_start() -> None:
    """Индекс в голове файла: окно не уходит в минус, а начинается с нуля."""
    served = Served(DATA)
    near = Window(served, 1000, 4096)

    assert served.asked == [(0, 5096)]
    assert near.tail(1000) == DATA[1000:5096]
