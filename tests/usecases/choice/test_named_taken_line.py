"""Зеркало :mod:`torrcast.usecases.choice.named_taken_line`: строка стража имени.

Строка обязана назвать взятую картину, честную причину - свою для живой и для мёртвой
названной, - число подошедших и ключ ``--menu``. Строка, врущая про причину, - дефект.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, plan
from torrcast.usecases.choice.named_taken_line import named_taken_line


def test_a_dead_named_picture_is_named_with_the_reason() -> None:
    """«блич s1e1»: названная не играет - причина сказана словами, взятая - рядом с ней."""
    bleach = [
        plan("Блич", 2004, kind="tv", seeders=3, asked_series=True),
        plan("Блич: Тысячелетняя кровавая война", 2022, kind="tv", seeders=40, asked_series=True),
    ]

    with outside(Outside()):
        assert named_taken_line(bleach, "блич", 2) == (
            "«блич» - это «Блич (2004, сериал)», но не играет: рой у неё мёртв - сидов 3; "
            "беру самую живую - «Блич: Тысячелетняя кровавая война (2022, сериал)»; "
            "всего подошло картин 2; другая: cast блич --menu"
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
        assert named_taken_line(chernobyl, "чернобыль", 3) == (
            "«чернобыль» - это «Чернобыль (2019, сериал)», «Чернобыль (2022, сериал)»; "
            "беру самую живую из них - «Чернобыль (2019, сериал)»; "
            "всего подошло картин 4; другая: cast чернобыль --menu"
        )
