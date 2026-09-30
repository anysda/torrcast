"""Зеркало :mod:`torrcast.domain.frames.mkv.probes`: куда ставить пробы честности.

Мера про одно: проба стоит запроса к рою на старте, и место каждой обязано что-то
доказывать. Фиксированные доли ленты не доказывают ничего - под них подстраивается шаг
настоящих опорных кадров, и врун проходит; соседняя пара доказывает счётом.
"""

from __future__ import annotations

from torrcast.domain.frames.keymap.point import Point
from torrcast.domain.frames.mkv.cue import Cue
from torrcast.domain.frames.mkv.probes import REACH, probes
from torrcast.domain.warm_open import HEAD_WARM

#: Индекс лежит за последним кластером, в хвосте файла: так его кладёт большинство
#: муксеров, и так лежали все четыре файла замера 30-09.
TAIL = 1 << 40


def _index(count: int, inside: int = 0) -> list[Cue]:
    """Индекс из ``count`` точек: своя точка на свой кластер, шаг по байтам ровный."""
    return [Cue(Point(k * 2.0, 4096 + k * 8192, 1), inside) for k in range(count)]


def test_the_probes_are_two_neighbour_pairs_and_not_shares_of_the_tape() -> None:
    """Пробы стоят парами подряд: между соседями нет точки, которую индекс мог бы подсунуть.

    Ровно этим соседство и берёт выравненного вруна: настоящий опорный кадр у него стоит
    через ровный шаг, а два соседа в один шаг не помещаются.
    """
    picked = probes(_index(384), TAIL)

    where = [point.at for point, _ in picked]
    assert len(picked) == 4, "две пары - каждая лишняя проба это Range-запрос на старте"
    assert where[1] - where[0] == 2.0, "соседние точки индекса, а не доли ленты"
    assert where[3] - where[2] == 2.0, "и вторая пара - соседи"


def test_the_first_pair_reads_the_head_and_the_second_the_end_of_the_tape() -> None:
    """Первая пара - в начале ленты, вторая - у индекса, а он лежит в самом конце.

    Лента по мегабайту на точку: середина лежит в 192 МБ от начала, то есть в месте
    раздачи, куда первый сегмент не ходит, и заход туда оплачивается только пробой. Голову
    рой отдаёт показу всё равно, а конец ленты лежит рядом с только что прочитанным
    индексом. Одна пара в голове пропускала бы файл, честный только в начале.
    """
    row = [Cue(Point(k * 2.0, 4096 + k * (1 << 20), 1), 0) for k in range(384)]

    picked = probes(row, TAIL)

    assert all(point.offset < HEAD_WARM for point, _ in picked[:2]), "первая пара в голове"
    assert [point.at for point, _ in picked[2:]] == [764.0, 766.0], "вторая - в конце ленты"


def test_the_second_pair_sits_next_to_the_index_wherever_the_muxer_put_it() -> None:
    """Вторая пара берётся у индекса: эти байты рой отдал только что, и заход туда дёшев.

    Индекс в голове - вторая пара совпадает с первой, и хвост не читается вовсе: заход в
    дальний хвост холодной раздачи держал бы старт до отказа роя (до 120 с), а показу эти
    байты не нужны. Индекс посередине файла - пара рядом с ним, а не в конце ленты.
    """
    row = [Cue(Point(k * 2.0, 4096 + k * (1 << 20), 1), 0) for k in range(384)]

    head = probes(row, 1024)
    middle = probes(row, row[200].point.offset + 4096)

    assert len(head) == 2, "индекс в голове - пара одна, хвост не читается"
    assert all(point.offset < HEAD_WARM for point, _ in head), "проба не уходит из головы"
    assert [point.at for point, _ in middle[2:]] == [400.0, 402.0], "пара у самого индекса"


def test_a_lying_step_that_divides_the_old_shares_does_not_divide_a_pair() -> None:
    """Шаг 48 делит середину и четверти нацело, а пару - нет: одна из двух ему чужая."""
    picked = probes(_index(2880), TAIL)

    for pair in (picked[:2], picked[2:]):
        numbers = [round(point.at / 2.0) for point, _ in pair]
        assert [n % 48 == 0 for n in numbers].count(True) <= 1, "обе на шаг вруна не сядут"


def test_a_probe_is_not_spent_on_a_block_it_would_not_reach() -> None:
    """Точку, чей блок лежит дальше окна пробы, обходим: запрос был бы впустую.

    Место блока внутри кластера лежит в самом индексе, поэтому обход не стоит запросов.
    У собранного вруна так молчали 2101 точка из 2880 - две трети индекса.
    """
    row = _index(40)
    row = [cue if k < 8 else Cue(cue.point, REACH) for k, cue in enumerate(row)]

    picked = probes(row, TAIL)

    assert all(inside < REACH for _, inside in picked), "проба смотрит туда, где что-то видно"


def test_a_pair_never_asks_the_same_block_twice() -> None:
    """Две точки на один кластер без места внутри - это один блок и одна проба впустую."""
    row = [Cue(Point(k * 2.0, 4096 + (k // 2) * 8192, 1), 0) for k in range(40)]

    picked = probes(row, TAIL)

    for (one, _), (other, _) in (picked[:2], picked[2:]):
        assert one.offset != other.offset, "пара спрашивает два разных кадра"


def test_the_pair_is_taken_in_time_order_whatever_order_the_index_lay_in() -> None:
    """Соседство считается по времени: индекс вправе лежать вперемешку, пара - нет."""
    picked = probes(list(reversed(_index(40))), TAIL)

    where = [point.at for point, _ in picked]
    assert where[1] - where[0] == 2.0
    assert where[3] - where[2] == 2.0


def test_too_few_points_are_not_worth_a_request() -> None:
    """Точек меньше четырёх - карту всё равно отвергнет сетка, платить рою незачем."""
    assert probes(_index(3), TAIL) == []
