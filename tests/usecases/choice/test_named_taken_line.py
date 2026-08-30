"""Зеркало :mod:`torrcast.usecases.choice.named_taken_line`: строка стража имени.

Строка обязана назвать взятую картину, честную причину - свою для живой и для мёртвой
названной, - число подошедших и ключ ``--menu``. Строка, врущая про причину, - дефект.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, plan
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.named_taken_line import named_taken_line


def q(*names: str) -> str:
    """Имена картин так, как их пишет каталог: в кавычках своего языка, через запятую."""
    return ", ".join(phrase("choice.quoted", it=name) for name in names)


def test_a_dead_named_picture_is_named_with_the_reason() -> None:
    """«блич s1e1»: названная не играет - причина сказана словами, взятая - рядом с ней."""
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    with outside(Outside()):
        assert named_taken_line(bleach, "блич", 2) == phrase(
            "choice.named_taken_unplayable",
            name="блич",
            whom=q(f"Блич (2004{phrase('choice.series_mark')})"),
            why=phrase("choice.why_dead_swarm", seeds=3),
            took=f"Блич: Тысячелетняя кровавая война (2022{phrase('choice.series_mark')})",
            total=2,
            asked="блич",
        )


def test_living_named_pictures_make_the_take_the_liveliest_of_them() -> None:
    """«чернобыль s1e5»: названные живы - взятая просто самая живая из них, и так и сказано."""
    chernobyl = [
        plan("Чернобыль: Последнее предупреждение", 1991, seeders=10, asked_series=True),
        plan("Чернобыль. Зона отчуждения", 2014, kind="tv", seeders=60, asked_series=True),
        plan("Чернобыль", 2019, kind="tv", seeders=79, asked_series=True),
        plan("Чернобыль", 2022, kind="tv", seeders=50, asked_series=True),
    ]

    with outside(Outside()):
        assert named_taken_line(chernobyl, "чернобыль", 3) == phrase(
            "choice.named_taken_alive",
            name="чернобыль",
            whom=q(
                f"Чернобыль (2019{phrase('choice.series_mark')})",
                f"Чернобыль (2022{phrase('choice.series_mark')})",
            ),
            took=f"Чернобыль (2019{phrase('choice.series_mark')})",
            total=4,
            asked="чернобыль",
        )
