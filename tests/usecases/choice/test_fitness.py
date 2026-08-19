"""Зеркало :mod:`torrcast.usecases.choice.fitness`: раздача, которой правда стоит смотреть.

От :func:`liveliness` мерка отличается двумя условиями, и оба взяты у самого отбора:
раздача жива своим роем и не старьё. Нужна она там, где вопрос не «кто живее», а
«состоится ли вечер вообще».
"""

from __future__ import annotations

from tests.usecases.choice.world import film, plan
from torrcast.usecases.choice.fitness import fitness
from torrcast.usecases.choice.liveliness import liveliness


def test_old_junk_is_not_something_worth_watching_however_lively_its_swarm_is() -> None:
    """Старьё в вес не идёт: 480p с сотней сидов - это не «есть чем смотреть».

    Приговор тут тот же, что выносит отбор каждой строке (:func:`is_dated`), а не
    отдельная мерка: разойдись они - тупиковая картина считалась бы живой у одной
    мерки и мёртвой у другой, и дефолт садился бы на неё при живой тёзке рядом.
    """
    sd_only = plan(pool=[film("Кино 2020 WEB-DLRip 480p", seeders=100, quality="480p")])

    assert liveliness(sd_only) == 100, "годной по правилам отбора раздача остаётся"
    assert fitness(sd_only) == 0, "а смотреть картину нечем: живого HD у неё нет"


def test_a_russian_evening_counts_only_releases_whose_name_promises_a_russian_track() -> None:
    """``dubbed`` - тот же вопрос про вечер, только по-русски (TC-178).

    Русская дорожка входит в «включилось», и пул без единой играбельной раздачи с нею -
    такой же тупик, как пул без единой играбельной вовсе. Сочти тут любую раздачу - и
    картина без русской дорожки объявлялась бы годной для русского вечера.
    """
    mixed = plan(
        pool=[
            film("Кино 2020 WEB-DL 1080p", seeders=100),
            film("Кино 2020 WEB-DL 1080p Дубляж", seeders=40),
        ]
    )

    assert fitness(mixed) == 100, "без оговорки считаются все годные живые раздачи"
    assert fitness(mixed, dubbed=True) == 40, "по-русски играет только обещавшая дорожку"


def test_a_picture_whose_whole_pool_is_unfit_weighs_nothing() -> None:
    """Ни одной годной живой не-старой раздачи - это ноль, а не «почти ноль».

    Ноль тут ответ, а не отсутствие ответа: по нему картина и признаётся тупиковой.
    """
    dead_end = plan(pool=[film("Кино 2020 DVDRip XviD", seeders=100, codec="XviD", quality=None)])

    assert fitness(dead_end) == 0
