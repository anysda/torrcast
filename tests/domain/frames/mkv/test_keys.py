"""Зеркало :mod:`torrcast.domain.frames.mkv.keys`: индекс ``Cues`` в карту опорных кадров.

Мера про две вещи, и обе стоили проекту суток. Первая - ПРАВДА карты: время из ``Cues``
считается масштабом файла, а смещение обязано быть абсолютным, потому что рой знает только
байты от начала файла. Вторая - ЦЕНА: заходов к рою ровно два, и оба минимальные.
"""

from __future__ import annotations

import pytest

from tests.domain.frames.mkv.blocks import Matroska
from tests.domain.frames.mp4.boxes import Served
from torrcast.domain.frames.keymap.key_map import KeyMap
from torrcast.domain.frames.mkv.keys import keys
from torrcast.domain.infra_error import InfraError

HEAD = 256


def _map(film: Matroska, head: int = HEAD) -> tuple[Served, int, KeyMap]:
    data, base = film.bytes()
    served = Served(data)
    return served, base, keys(served, served.read(0, head))


def test_the_cue_times_and_absolute_offsets_make_the_map() -> None:
    """Время считано масштабом файла, а смещение отсчитано от начала ФАЙЛА, не Segment.

    Отдай разбор позицию как есть - рой грелся бы не в том месте на всю длину головы.
    """
    served, base, found = _map(Matroska())

    assert found.kind == "mkv"
    assert found.duration == 6.0, "длительность - это Duration в своём масштабе"
    assert [(p.at, p.offset, p.track) for p in found.points] == [
        (0.0, base + 100, 1),
        (0.5, base + 4000, 1),
    ]
    assert found.requests == served.requests


def test_the_map_comes_out_sorted_whatever_order_the_index_lay_in() -> None:
    """Точки едут наружу по времени: сетку сегментов строят по возрастанию, а не по файлу."""
    _served, _base, found = _map(Matroska(cues=[(900, 9000, 1), (100, 1000, 1)]))

    assert [p.at for p in found.points] == [0.1, 0.9]


def test_the_cues_of_sound_and_subtitles_keep_their_own_track_number() -> None:
    """У «Моаны 2» шесть дорожек в Cues: смешай их - и сетка встала бы по звуку."""
    _served, _base, found = _map(Matroska(cues=[(0, 100, 1), (0, 100, 2), (700, 800, 2)]))

    assert sorted({p.track for p in found.points}) == [1, 2]


def test_a_small_head_is_reread_in_full_instead_of_giving_up() -> None:
    """Маленького куска не хватило на SeekHead - берём голову целиком, а не сдаёмся.

    Это второй заход и единственный законный: длинный SeekHead и толстые теги - обычное
    дело, и карта из-за них теряться не имеет права.
    """
    served, _base, found = _map(Matroska(), head=16)

    assert found.points, "с полной головы индекс всё равно нашёлся"
    assert served.requests == 3, "первый кусок, полная голова и один заход за Cues"


def test_a_file_without_an_index_says_so_instead_of_reading_the_film() -> None:
    """Нет записи о ``Cues`` - честная ошибка: перебирать кластеры фильма незачем."""
    data, _base = Matroska(forget_cues=True).bytes()
    reader = Served(data)

    with pytest.raises(InfraError, match="Cues"):
        keys(reader, reader.read(0, HEAD))


def test_something_that_is_not_matroska_is_named_as_such() -> None:
    """Нет ``Segment`` - это не mkv, и говорится это прямо."""
    reader = Served(b"\x00" * 512)

    with pytest.raises(InfraError, match="Segment"):
        keys(reader, reader.read(0, HEAD))
