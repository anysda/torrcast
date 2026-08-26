"""Зеркало :mod:`torrcast.usecases.choice._shown`: печать списка картин меню.

Вопрос тут один и он про справку: ждать её перед печатью или дописывать в напечатанное.
Ответ на него зависит от того, СМОТРИТ ли кто-то на список в эту секунду, а не от того,
кто и зачем список поднял.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, Waited, parts
from torrcast.usecases.choice._shown import _shown

MOANA = (
    ("Моана: романтика золотого века", 1926, 1),
    ("Моана", 2016, 222),
    ("Моана 2", 2024, 140),
)


def test_the_list_goes_out_before_the_reference_and_never_waits_for_it() -> None:
    """🔴 Решение владельца: список печатается сразу, а рейтинг дописывается в его строку.

    Ждать справку меню тут не вправе: полторы секунды ожидания человек платил и на двух
    прогонах из трёх всё равно получал голый список.
    """
    world = Outside()
    facts = Waited()

    _shown(world, parts(*MOANA), facts, dress=True, asked="моана").close()

    assert facts.waits == 0, "живой экран и вопрос - справку дописывают, а не ждут"
    assert world.said[0].splitlines() == [
        "  1. Моана: романтика золотого века (1926)",
        "  2. Моана (2016)",
        "  3. Моана 2 (2024)",
    ]


def test_where_nobody_will_watch_the_line_grow_the_reference_is_awaited() -> None:
    """Дописывать некому - лучше подождать и напечатать со справкой, чем голое навсегда.

    Два таких случая: вопроса не будет вовсе (номер назвал сам человек), и вывод ушёл не на
    экран, а в трубу или в файл. И там, и там показанную строку уже ничем не переписать.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    silent = Waited()
    _shown(Outside(), mummy, silent, dress=False, asked="мумия").close()
    piped = Waited()
    _shown(Outside(live=False), mummy, piped, dress=True, asked="мумия").close()

    assert (silent.waits, piped.waits) == (1, 1)


def test_the_shown_order_is_remembered_as_the_address_of_every_number() -> None:
    """Номер пункта - адрес: под ним в следующем запуске обязана стоять ТА же картина."""
    world = Outside()

    _shown(world, parts(*MOANA), None, dress=True, asked="моана").close()

    assert world.remembered == [
        (
            "моана",
            [
                (
                    "movie:моана-романтика-золотого-века:1926",
                    "Моана: романтика золотого века (1926)",
                ),
                ("movie:моана:2016", "Моана (2016)"),
                ("movie:моана-2:2024", "Моана 2 (2024)"),
            ],
        )
    ]
