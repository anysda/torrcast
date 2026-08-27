"""Зеркало :mod:`torrcast.usecases.choice._dress`: справка дописывается в стоящую строку.

🔴 Решение владельца: меню показывается сразу, а рейтинг дописывается в уже показанную
строку - зритель видит, как она дополняется. Проверяется тут именно это: что переписана
та самая строка того самого пункта и что зря экран не мигает.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterable

from tests.usecases.choice.world import Outside, Paint, outside, parts
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.usecases.choice._dress import _dress
from torrcast.usecases.choice.menu_blocks import menu_blocks
from torrcast.usecases.facts import Facts
from torrcast.usecases.select.plan import Plan

Blurbs = dict[tuple[str, int | None], Fact]
CARS = ("Тачки", 2006)
CARS2 = ("Тачки 2", 2011)
DRESSED = Fact(rating="IMDb 7.1", runtime="1 ч 57 мин")


class Empty:
    """Кэш, в котором нет ничего: за всей справкой идут в сеть."""

    def __init__(self, ready: Blurbs | None = None) -> None:
        self.ready = ready or {}

    def blurbs(self, wanted: list[tuple[str, int | None]]) -> Blurbs:
        return {key: self.ready[key] for key in wanted if key in self.ready}

    def remember(self, found: Blurbs, misses: Iterable[tuple[str, int | None]] = ()) -> None:
        return None


class Wave:
    """Источник, отвечающий волнами: сперва описания, потом украшения к ним."""

    def __init__(self, first: Blurbs, second: Blurbs, hold: threading.Event | None = None) -> None:
        self.first = first
        self.second = second
        #: Чем волну придержать: без этого она приезжает раньше, чем меню напечатано.
        self.hold = hold

    def fetch(
        self,
        wanted: list[tuple[str, int | None]],
        timeout: float = HTTP_TIMEOUT,
        ready: Callable[[Blurbs], None] | None = None,
        kinds: dict[tuple[str, int | None], str] | None = None,
    ) -> tuple[Blurbs, set[tuple[str, int | None]]]:
        if self.hold is not None:
            self.hold.wait(2.0)
        if ready is not None:
            ready(self.first)
        return self.second, set(wanted)


def stand(
    plans: list[Plan], facts: Facts, world: Outside | None = None
) -> tuple[Paint, list[list[str]]]:
    """Показанное меню: куски посчитаны, список напечатан - ровно как в сценарии выбора."""
    with outside(world or Outside()):
        blocks = menu_blocks(plans, facts)
    paint = Paint(said=[])
    paint.show([line for block in blocks for line in block])
    return paint, blocks


def test_the_reference_that_arrived_after_the_menu_is_written_into_its_line() -> None:
    """Справка приехала, когда список уже на экране, - и она дописывается в его строку."""
    cars = parts(("Тачки", 2006, 66))
    facts = Facts([CARS], store=Empty(), source=Wave({}, {CARS: DRESSED}))
    paint, blocks = stand(cars, facts)

    _dress(paint, cars, blocks, facts)
    facts.start()
    facts.finish()

    assert paint.redraws == [(0, "  1. Тачки (2006) · IMDb 7.1 · 1 ч 57 мин")]
    assert paint.lines == ["  1. Тачки (2006) · IMDb 7.1 · 1 ч 57 мин"]


def test_a_reference_that_beat_the_subscription_is_not_lost() -> None:
    """Справка успела приехать между печатью и подпиской - строка всё равно дописана.

    Окно тут в миллисекунды, но справка, лежащая в руках при голом меню, - это ровно та
    поломка, ради которой всё и затевалось.
    """
    cars = parts(("Тачки", 2006, 66))
    facts = Facts([CARS], store=Empty(), source=Wave({}, {CARS: DRESSED}))
    paint, blocks = stand(cars, facts)
    facts.start()
    facts.finish()

    _dress(paint, cars, blocks, facts)

    assert paint.redraws == [(0, "  1. Тачки (2006) · IMDb 7.1 · 1 ч 57 мин")]


def test_a_line_that_did_not_change_is_not_rewritten_at_all() -> None:
    """Справки нет - экран не мигает: переписывать строку тем же самым текстом незачем."""
    cars = parts(("Тачки", 2006, 66))
    facts = Facts([CARS], store=Empty(), source=Wave({}, {}))
    paint, blocks = stand(cars, facts)

    _dress(paint, cars, blocks, facts)
    facts.start()
    facts.finish()

    assert paint.redraws == []


def test_the_line_of_the_second_picture_is_found_under_the_description_of_the_first() -> None:
    """Место строки считается по кускам: у картины с описанием их несколько.

    Считай меню сплошным списком - и рейтинг второй картины лёг бы в строку описания
    первой, то есть в чужой пункт.
    """
    cars = parts(("Тачки", 2006, 66), ("Тачки 2", 2011, 40))
    hold = threading.Event()
    facts = Facts(
        [CARS, CARS2],
        store=Empty({CARS: Fact(about="Мультфильм студии Pixar о гоночном автомобиле.")}),
        source=Wave({}, {CARS2: DRESSED}, hold),
    )
    facts.start()  # описание первой картины лежит в кэше, украшения второй ещё в пути
    paint, blocks = stand(cars, facts)

    _dress(paint, cars, blocks, facts)
    hold.set()
    facts.finish()

    assert len(blocks[0]) == 2, "у первой картины есть описание, и оно занимает свою строку"
    assert paint.redraws == [(2, "  2. Тачки 2 (2011) · IMDb 7.1 · 1 ч 57 мин")]


def test_a_description_that_came_late_adds_no_lines_to_the_menu_on_screen() -> None:
    """Опоздавшее описание в список не вставляется: он поехал бы под читающим человеком.

    Дописывается ровно строка пункта; описание достанется следующему меню из кэша.
    """
    cars = parts(("Тачки", 2006, 66))
    late = Fact(about="Мультфильм студии Pixar.", rating="IMDb 7.1")
    facts = Facts([CARS], store=Empty(), source=Wave({}, {CARS: late}))
    paint, blocks = stand(cars, facts)

    _dress(paint, cars, blocks, facts)
    facts.start()
    facts.finish()

    assert paint.lines == ["  1. Тачки (2006) · IMDb 7.1"]
