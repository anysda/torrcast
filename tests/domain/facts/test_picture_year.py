"""Проверяет чтение года САМОЙ картины из статьи."""

from tests.articles import CARS, CLIMBERS, FARGO_SERIES, MASTER_2005
from torrcast.domain.facts.picture_year import picture_year


def test_a_year_named_only_once_is_still_trusted() -> None:
    """Молчать в ответ на любой год - перебор: спутать единственный год не с чем.

    У «Мастера и Маргариты» паспортная фраза года не называет вовсе, но во всей врезке он
    один - 2005. Отказ от него стоил бы гейту добора умения отличать сериал 2005 года от
    фильма 2024-го, а это ровно то, ради чего год и спрашивают.
    """
    assert picture_year(MASTER_2005) == 2005
    # Названо несколько - выбирать между ними нечем.
    assert picture_year(FARGO_SERIES) is None
    # Паспортная фраза сильнее всего остального.
    assert picture_year(CARS) == 2006
    assert picture_year(CLIMBERS) == 2019
