"""Зеркало :mod:`torrcast.domain.frames.mp4._window`: чтение ``moov` только вперёд.

Мера тут про ЦЕНУ, а не про правильность разбора: у холодной раздачи каждый лишний заход
и каждый лишний мегабайт - это секунды старта. Окно обязано ходить подряд и обрываться
там, где разбору перестало быть нужно, а перечисление детей - не вычитывать последнего
ради первого.
"""

from __future__ import annotations

from tests.domain.frames.mp4.boxes import Movie, Served, box
from torrcast.domain.frames.mp4._window import MOOV_CHUNK, _boxes, _find, _full, _table, _Window


def test_the_window_reads_forward_in_chunks_and_never_twice() -> None:
    """Куски ложатся подряд: для роя это лучший из возможных запросов."""
    served = Served(b"\x00" * (4 * MOOV_CHUNK))
    window = _Window(served, 0, 4 * MOOV_CHUNK)

    window.need(10)
    window.need(20)
    first = list(served.asked)
    window.need(MOOV_CHUNK + 5)

    assert first == [(0, MOOV_CHUNK)], "второй вопрос о тех же байтах не задан"
    assert served.asked[1][0] == MOOV_CHUNK, "следующий кусок начинается там, где кончился прежний"


def test_the_window_never_reads_past_its_own_box() -> None:
    """Окно кончается вместе с боксом: за его хвостом лежит чужое."""
    served = Served(b"\x00" * 1000)
    window = _Window(served, 100, 40)

    window.need(10_000)

    assert served.asked == [(100, 40)]


def test_children_are_walked_lazily_and_the_first_match_stops_the_read() -> None:
    """Дети - генератор, а не список: иначе первый ребёнок стоил бы всех остальных.

    У «Моаны 2» дорожка звука лежит за дорожкой видео, и списком разбор вычитывал 5.26 МБ
    ради 2.08 МБ, которые ему нужны.
    """
    payload = box(b"aaaa", b"\x00" * 16) + box(b"bbbb", b"\x00" * (2 * MOOV_CHUNK))
    served = Served(box(b"moov", payload))
    window = _Window(served, 0, len(served.data))

    kind, data, end = next(_boxes(window, 8, len(served.data)))

    assert kind == b"aaaa"
    assert served.taken <= MOOV_CHUNK, "хвост второго ребёнка читать было незачем"
    assert (data, end) == (16, 32)


def test_find_returns_the_asked_child_and_nothing_for_a_missing_one() -> None:
    """Поиск ребёнка по типу: нашёлся - границы, не нашёлся - ``None``, а не выдумка."""
    served = Served(Movie().bytes())
    head = served.read(0, 512)
    window = _Window(served, 0, len(served.data), head)

    moov = _find(window, 0, len(served.data), b"moov")

    assert moov is not None
    assert _find(window, *moov, b"mvhd") is not None
    assert _find(window, *moov, b"none") is None


def test_a_full_box_header_and_a_table_header_are_read_the_same_way_everywhere() -> None:
    """Версия ``FullBox`` и счётчик записей таблицы - там, где их кладёт стандарт."""
    rows = box(b"stco", bytes([1]) + b"\x00" * 3 + (3).to_bytes(4, "big") + b"\x00" * 12)
    served = Served(rows)
    window = _Window(served, 0, len(rows))

    version, after = _full(window, 8)
    at, count = _table(window, 8, len(rows), 4)

    assert (version, after) == (1, 12)
    assert (at, count) == (16, 3), "записи начинаются за счётчиком, и их ровно столько"


def test_a_table_never_promises_more_rows_than_the_box_holds() -> None:
    """Счётчик из битого файла не имеет права увести чтение за конец бокса."""
    lying = box(b"stco", bytes(4) + (1000).to_bytes(4, "big") + b"\x00" * 8)
    served = Served(lying)
    window = _Window(served, 0, len(lying))

    _at, count = _table(window, 8, len(lying), 4)

    assert count == 2
