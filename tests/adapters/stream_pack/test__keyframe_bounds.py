"""Проверяет счёт границ сетки по опорным кадрам: шаг, потолок байт, голова и хвост."""

from itertools import pairwise

from torrcast.adapters.stream_pack._keyframe_bounds import _keyframe_bounds

#: Опорный кадр каждые две секунды на минуту фильма.
KEYS = [round(k * 2.0, 3) for k in range(31)]
DURATION = 60.0


def _bounds(
    step: float,
    sizes: list[int] | None = None,
    cap: float = 1e18,
    extra_mbit: float = 0.0,
    ceiling_mbit: float = 0.0,
    fixed_mbit: float = 0.0,
    span_cap: float = 0.0,
) -> tuple[float, ...]:
    found, _copy = _keyframe_bounds(
        KEYS,
        DURATION,
        step,
        sizes or [],
        extra_mbit,
        ceiling_mbit,
        cap,
        fixed_mbit,
        span_cap=span_cap,
    )
    return found


def test_the_next_boundary_is_the_first_keyframe_not_earlier_than_the_step() -> None:
    """Сцена-вспышка (много опорных кадров подряд) не дробит весь манифест.

    Граница всегда стоит НА опорном кадре: иначе кусок не декодируется сам по себе, и
    перемотка в него показывает картинку не сразу.
    """
    found = _bounds(step=10.0)
    assert found[0] == 0.0
    assert all(place in KEYS for place in found)
    assert all(10.0 <= later - prev < 12.0 for prev, later in pairwise(found))


def test_a_piece_heavier_than_the_cap_is_cut_shorter() -> None:
    """🔴 Приёмник Q70D срывается в BUFFERING на сегменте тяжелее ~19 МБ, сколько бы секунд
    в нём ни было. Потолок веса главнее шага, и кусок становится короче.
    """
    sizes = [int(place * 2.0e6) for place in KEYS]  # 2 МБ в секунду
    heavy = _bounds(step=10.0, sizes=sizes, cap=1e18)
    light = _bounds(step=10.0, sizes=sizes, cap=8.0e6)
    assert max(b - a for a, b in pairwise(light)) < max(b - a for a, b in pairwise(heavy)), (
        "потолок веса не укоротил ни одного куска"
    )
    assert all(place in KEYS for place in light), "резать GOP нельзя даже ради потолка"


def test_the_head_may_take_the_nearest_keyframe_from_either_side() -> None:
    """🔴 На «Моане» 2016 прежняя сетка брала 14.890 вместо ближайших 9.927 дважды подряд,
    и живой Q70D молча закрывал медиасессию после такой головы.
    """
    sparse = [0.0, 9.0, 16.0, 26.0, 36.0, 46.0, 56.0]
    found, _copy = _keyframe_bounds(sparse, DURATION, 10.0, [], 0.0, 0.0, 1e18, 0.0)
    assert found[1] == 9.0, "голова взяла дальний кадр вместо ближайшего"


def test_a_short_tail_sticks_to_the_last_piece() -> None:
    """Пара секунд в манифесте лишним куском не стоит: хвост прилипает к последнему."""
    found = _bounds(step=10.0)
    assert DURATION - found[-1] < 10.0 * 1.5
    assert found[-1] <= DURATION - 10.0 / 2


def test_the_copy_weigher_knows_no_ceiling() -> None:
    """Бюджет прогрева считается под ПИКОВЫЙ вес: на диск кусок ложится копией, во весь вес."""
    sizes = [int(place * 2.0e6) for place in KEYS]
    _found, copy = _keyframe_bounds(KEYS, DURATION, 10.0, sizes, 0.0, 1.0, 1e18, 0.0)
    assert copy is not None
    assert copy(0.0, 10.0) > 1.0 * 10.0 * 1e6 / 8, "вес копии зажат потолком перекода"

    _found, none = _keyframe_bounds(KEYS, DURATION, 10.0, [], 0.0, 0.0, 1e18, 0.0)
    assert none is None, "карты нет - и веса копии знать неоткуда"


def test_a_piece_longer_than_the_length_ceiling_is_cut_shorter() -> None:
    """🔴 Приставка Android TV просит следующий кусок, когда впереди остаётся 20.0 с
    плёнки: кусок такой же длины оставляет её с единственным куском в запасе, и на
    границе после него она сама встаёт на паузу. Потолок длины судит кандидата так же,
    как потолок веса.
    """
    sparse = [round(k * 6.0, 3) for k in range(11)]
    tall, _copy = _keyframe_bounds(sparse, DURATION, 10.0, [], 0.0, 0.0, 1e18, 0.0)
    short, _copy = _keyframe_bounds(sparse, DURATION, 10.0, [], 0.0, 0.0, 1e18, 0.0, span_cap=8.0)

    assert max(b - a for a, b in pairwise(tall)) == 12.0, "без потолка длины сетка берёт 12 с"
    assert max(b - a for a, b in pairwise(short)) == 6.0, "потолок длины не укоротил куски"
    assert all(place in sparse for place in short), "резать GOP нельзя даже ради потолка"


def test_a_gop_longer_than_the_ceiling_stays_whole() -> None:
    """Резать GOP нельзя, и врать об этом не будем: длинный кадр остаётся длинным куском."""
    single = [0.0, 30.0, 40.0, 50.0]
    found, _copy = _keyframe_bounds(single, DURATION, 10.0, [], 0.0, 0.0, 1e18, 0.0, span_cap=8.0)

    assert found[1] == 30.0


def test_a_zero_length_ceiling_does_not_move_a_single_boundary() -> None:
    """Ноль - это «потолка нет»: осторожная сетка обязана остаться прежней знак в знак."""
    sizes = [int(place * 2.0e6) for place in KEYS]

    assert _bounds(step=10.0, sizes=sizes, cap=8.0e6, span_cap=0.0) == _bounds(
        step=10.0, sizes=sizes, cap=8.0e6
    )
