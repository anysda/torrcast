"""Зеркало :mod:`torrcast.usecases.choice._shown`: печать списка картин меню.

Вопрос тут один и он про справку: ждать её перед печатью или дописывать в напечатанное.
Ответ на него зависит от того, СМОТРИТ ли кто-то на список в эту секунду, а не от того,
кто и зачем список поднял.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from tests.articles import MOANA as MOANA_ARTICLE
from tests.fakes.blurb_store import FakeBlurbStore
from tests.usecases.choice.world import Outside, Waited, parts
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.settings import HTTP_TIMEOUT
from torrcast.usecases.choice._shown import _shown
from torrcast.usecases.facts import Facts

MOANA = (
    ("Моана: романтика золотого века", 1926, 1),
    ("Моана", 2016, 222),
    ("Моана 2", 2024, 140),
)


def test_the_list_waits_for_the_blurb_but_never_for_its_ornaments() -> None:
    """🔴 TC-717. Решение владельца от 20-08-2026, вариант «б»: описание ценой ожидания.

    Дописать описание в показанный список нечем - оно занимает несколько своих строк, и
    вставить их под курсором значило бы сдвинуть весь список у читающего человека. Значит,
    ждать его надо ДО печати, иначе незнакомая картина остаётся без описания навсегда.
    Рейтинг с хронометражем при этом не ждут как не ждали: они дописываются в готовую
    строку у зрителя на глазах.
    """
    world = Outside()
    facts = Waited()

    _shown(world, parts(*MOANA), facts, dress=True, asked="моана").close()

    assert (facts.abouts, facts.waits) == (1, 0), "ждут описание, а не всю справку"
    assert world.said[0].splitlines() == [
        "  1. Моана: романтика золотого века (1926)",
        "  2. Моана (2016)",
        "  3. Моана 2 (2024)",
    ]


def test_the_first_cold_list_carries_the_blurb_under_its_item() -> None:
    """🔴 TC-717. Описание стоит под пунктом с ПЕРВОГО показа незнакомой картины.

    Мера тут - предмет решения владельца целиком, а не его половина: источник отдаёт
    описания первым шагом и залипает на втором, то есть к моменту печати не приехало ничего,
    кроме описаний. Список обязан выйти уже с ними - на холодном кэше второго шанса у
    описания нет.

    Часами тут не меряют намеренно: сон в источнике сделал бы меру гонкой, и на быстрой
    машине список успевал бы напечататься со справкой без всякого ожидания. Здесь описание
    физически не может попасть в список раньше, чем список за ним сел, - не сел, значит его
    там нет.
    """
    awaited, ornaments = threading.Event(), threading.Event()

    class Stepwise:
        """Описания приезжают ПОСЛЕ того, как список за ними сел; украшения - никогда."""

        def fetch(
            self,
            wanted: list[tuple[str, int | None]],
            timeout: float = HTTP_TIMEOUT,
            ready: Callable[[dict[tuple[str, int | None], Fact]], None] | None = None,
            kinds: dict[tuple[str, int | None], str] | None = None,
        ) -> tuple[dict[tuple[str, int | None], Fact], set[tuple[str, int | None]]]:
            awaited.wait(5.0)
            if ready is not None:
                ready({key: Fact(about=MOANA_ARTICLE) for key in wanted})
            ornaments.wait(5.0)
            return {}, set()

    class Stepped(Facts):
        """Помечает тот самый миг, когда список сел ждать описания."""

        def wait_about(self) -> None:
            awaited.set()
            super().wait_about()

    world = Outside()
    moana = parts(("Моана", 2016, 222), ("Моана 2", 2024, 140))
    facts = Stepped(
        [(p.picture.title, p.picture.year) for p in moana],
        5.0,
        store=FakeBlurbStore(),
        source=Stepwise(),
    )
    facts.start()
    try:
        _shown(world, moana, facts, dress=True, asked="моана").close()
    finally:
        facts.watch(None)
        awaited.set()
        ornaments.set()
        facts.finish()

    shown = world.said[0].splitlines()
    assert shown[0] == "  1. Моана (2016)"
    assert shown[1].startswith("     «Моа́на» (англ. Moana) —"), (
        f"описание обязано стоять под пунктом с первой печати, а список вышел: {shown}"
    )


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
    assert (silent.abouts, piped.abouts) == (0, 0), "дописывать некому - ждут справку целиком"


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
