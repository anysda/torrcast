"""Зеркало :mod:`torrcast.domain.frames.mkv.key_frame`: опорный ли кадр по содержимому.

Мера родилась из TC-639: флаг опорности в блоке и точка Cues - слова муксера, а он бывает
врёт; срез AVC - факт. Трёхзначный ответ проверяется целиком: IDR, не-IDR и «не
разобрать», потому что цена ошибки в обе стороны уже оплачена.
"""

from __future__ import annotations

from tests.domain.frames.mkv.blocks import AVC, Matroska
from tests.domain.frames.mp4.boxes import Served
from torrcast.domain.frames.mkv.key_frame import key_frame


def _served(film: Matroska) -> tuple[Served, int]:
    data, base = film.bytes()
    return Served(data), base


def test_an_idr_slice_is_a_key_frame() -> None:
    """У честного файла первый срез блока - IDR (NAL тип 5)."""
    served, base = _served(Matroska())

    assert key_frame(served, base + 1024, 1, AVC) is True


def test_a_non_idr_slice_behind_a_key_flag_is_a_ghost() -> None:
    """Флаг опорности стоит, а срез не IDR - точка Cues призрак, и видно это по байтам."""
    served, base = _served(Matroska(ghost=True))

    assert key_frame(served, base + 1024, 1, AVC) is False


def test_a_codec_we_cannot_read_is_not_a_verdict() -> None:
    """Не AVC - содержимое кадра нам не по зубам: «не разобрать», а не призрак."""
    served, base = _served(Matroska())

    assert key_frame(served, base + 1024, 1, "A_AC3") is None
    assert served.requests == 0, "чужой кодек не стоит ни одного запроса"


def test_a_laced_block_cannot_be_read() -> None:
    """Лейсинг блока не разбираем - честное «не разобрать», а не догадка."""
    served, base = _served(Matroska(laced=True))

    assert key_frame(served, base + 1024, 1, AVC) is None


def test_an_offset_without_a_cluster_cannot_be_read() -> None:
    """По смещению нет кластера - опять «не разобрать»: решение остаётся за вызывающим."""
    served, base = _served(Matroska())

    assert key_frame(served, base + 100, 1, AVC) is None
