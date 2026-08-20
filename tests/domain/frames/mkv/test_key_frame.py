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


def test_a_block_header_cut_by_the_window_edge_cannot_be_read() -> None:
    """Край окна лёг поперёк заголовка блока, а видеоблока в окне не было (TC-687).

    walk честно отдаёт запись, чьё тело осталось за границей прочитанного куска, и
    разбор обязан сказать «не разобрать», а не упасть: на пути показа ловится только
    InfraError, и любое другое исключение роняет показ вместо мягкого отката.
    """
    served, base = _served(Matroska(cues=[(0, 1024, 1)], cut_header=True))

    assert key_frame(served, base + 1024, 1, AVC) is None


def test_the_named_block_is_judged_and_not_the_first_one_in_the_cluster() -> None:
    """Перед названным кадром в кластере лежит чужой - судится всё равно названный.

    Точка Cues ссылается на НАЧАЛО кластера, а муксер вправе положить туда несколько
    видеокадров. Первым тогда оказывается чужой кадр, и честный индекс отвергался бы за
    него целиком; место названного блока муксер называет сам (``CueRelativePosition``).
    """
    film = Matroska(before=2, relative=True)
    served, base = _served(film)

    assert key_frame(served, base + 1024, 1, AVC, film.inside()) is True


def test_a_ghost_behind_an_honest_neighbour_in_the_same_cluster_is_seen() -> None:
    """Первый видеоблок кластера опорный, а названный точкой - нет: это призрак.

    Ровно так врущий индекс покупал бы себе проверку: сосед по кластеру отвечает за него.
    """
    film = Matroska(before=2, relative=True, ghost=True)
    served, base = _served(film)

    assert key_frame(served, base + 1024, 1, AVC, film.inside()) is False
