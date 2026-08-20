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
        (0.0, base + 1024, 1),
        (0.5, base + 4096, 1),
    ]
    assert found.requests == served.requests


def test_the_map_remembers_the_track_the_file_named() -> None:
    """Дорожку видео называет сам файл (``Tracks``) - карта везёт её номер с собой."""
    _served, _base, found = _map(Matroska())

    assert found.video == 1


def test_without_tracks_the_track_is_not_named_and_not_guessed_here() -> None:
    """``Tracks`` в голове нет - карта дорожку не называет: выбор остаётся эвристике."""
    _served, _base, found = _map(Matroska(forget_tracks=True))

    assert found.video is None


def test_a_lying_index_is_an_error_not_a_ghost_map() -> None:
    """Точки Cues ссылаются не на опорные кадры - карта из них не строится (TC-639).

    Замер на живом файле: муксер поставил точку на каждый кластер и флаг опорности на
    каждый видеоблок, и 7235 из 8065 «опорных кадров» через ровно 1.251 с оказались
    призраками.
    Четырёх точек хватает, чтобы проверка честности запустилась (меньше - карту отвергнет
    сама сетка), а врущему индексу - чтобы попасться первой же пробой.
    """
    cues = [(0, 1024, 1), (2000, 2048, 1), (4000, 3072, 1), (6000, 4096, 1)]
    data, _base = Matroska(cues=cues, ghost=True).bytes()
    reader = Served(data)

    with pytest.raises(InfraError, match="врёт"):
        keys(reader, reader.read(0, HEAD))


def test_an_honest_index_passes_the_frame_check() -> None:
    """Честный индекс: пробы находят IDR, карта строится, цена - запрос на каждую пробу."""
    cues = [(0, 1024, 1), (2000, 2048, 1), (4000, 3072, 1), (6000, 4096, 1)]
    data, base = Matroska(cues=cues).bytes()
    reader = Served(data)
    found = keys(reader, reader.read(0, HEAD))

    assert [(p.at, p.offset, p.track) for p in found.points] == [
        (0.0, base + 1024, 1),
        (2.0, base + 2048, 1),
        (4.0, base + 3072, 1),
        (6.0, base + 4096, 1),
    ]
    assert reader.requests == 5, "голова, один заход за Cues и три пробы вразброс"


def test_an_honest_index_survives_a_cluster_with_several_video_frames() -> None:
    """Опорный кадр не первым в кластере - индекс всё равно честный, и карта строится.

    Точка Cues ссылается на начало кластера, а муксер вправе положить туда несколько
    видеокадров: тогда первым лежит чужой кадр. Судить по нему - значит отвергнуть
    честный файл целиком и отдать показу ровную сетку вместо сетки по опорным кадрам.
    Место своего блока муксер называет сам (``CueRelativePosition``).
    """
    cues = [(0, 1024, 1), (2000, 2048, 1), (4000, 3072, 1), (6000, 4096, 1)]
    data, base = Matroska(cues=cues, before=2, relative=True).bytes()
    reader = Served(data)
    found = keys(reader, reader.read(0, HEAD))

    assert [p.offset for p in found.points] == [base + 1024, base + 2048, base + 3072, base + 4096]


def test_a_ghost_does_not_buy_itself_off_with_an_honest_neighbour() -> None:
    """Первый видеоблок кластера опорный, а названный точкой - призрак: индекс врёт.

    Так проверка честности покупается соседом по кластеру: муксер, который ставит точку
    на каждый видеокадр, начинает кластер настоящим опорным кадром, и проба по первому
    блоку каждый раз отвечает «опорный». Замер на стенде: 2880 точек при 60 настоящих
    опорных кадрах - 97.9 % призраков, и все три пробы сказали «честно».
    """
    cues = [(0, 1024, 1), (2000, 2048, 1), (4000, 3072, 1), (6000, 4096, 1)]
    data, _base = Matroska(cues=cues, before=2, relative=True, ghost=True).bytes()
    reader = Served(data)

    with pytest.raises(InfraError, match="врёт"):
        keys(reader, reader.read(0, HEAD))


def test_a_block_header_cut_by_the_window_edge_is_not_a_crash() -> None:
    """Окно пробы обрезало заголовок блока: «не разобрать», а не падение (TC-687).

    «Не разобрать» - не призрак: проверка честности верит такой точке, как верит
    незнакомому кодеку, - а упасть на пути показа она права не имеет, там ловится
    только InfraError.
    """
    cues = [(k * 500, 1024 + k * 262144, 1) for k in range(4)]
    data, _base = Matroska(cues=cues, cut_header=True).bytes()
    reader = Served(data)
    found = keys(reader, reader.read(0, HEAD))

    assert len(found.points) == 4, "пробы ответили «не разобрать» - индекс принят"


def test_the_map_comes_out_sorted_whatever_order_the_index_lay_in() -> None:
    """Точки едут наружу по времени: сетку сегментов строят по возрастанию, а не по файлу."""
    _served, _base, found = _map(Matroska(cues=[(900, 9000, 1), (100, 1000, 1)]))

    assert [p.at for p in found.points] == [0.1, 0.9]


def test_the_cues_of_sound_and_subtitles_keep_their_own_track_number() -> None:
    """У «Моаны 2» шесть дорожек в Cues: смешай их - и сетка встала бы по звуку."""
    _served, _base, found = _map(Matroska(cues=[(0, 1024, 1), (0, 1024, 2), (700, 2048, 2)]))

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
