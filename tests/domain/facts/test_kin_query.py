"""Зеркало :mod:`torrcast.domain.facts.kin_query`: строка SPARQL за родней картины."""

from torrcast.domain.facts.kin_query import kin_query


def test_both_series_and_chain_properties_are_asked_in_one_query() -> None:
    """Оба свойства едут одним походом: у части франшиз нет общего элемента серии."""
    query = kin_query("Q105598")

    assert "wd:Q105598 wdt:P179" in query
    assert "wd:Q105598 (wdt:P155|wdt:P156)*" in query
    assert query.count("wd:Q105598") == 4, "серия, цепочка, обратная ветка и фильтр"


def test_the_pictures_that_point_at_the_franchise_are_asked_too() -> None:
    """🔴 Обратная ветка: имя франшизы паспорт отдаёт статьёй САМОЙ франшизы.

    Франшиза частью себя не является, и прямые ветки на ней молчат. Картины смотрят на
    неё сами - через свою серию и «часть от» (`P361`), потому что между картиной и
    медиафраншизой стоит ещё и элемент серии. Замер 07-09-2026 по десяти франшизам
    ТЗ §8: без этой ветки полка пуста у четырёх из них.
    """
    assert "?item wdt:P179/wdt:P361* wd:Q216930" in kin_query("Q216930")


def test_the_asked_picture_is_filtered_out_of_its_own_kin() -> None:
    """P155/P156 со звёздочкой на нулевом шаге возвращает саму картину - её вычёркивает FILTER."""
    assert "FILTER(?item != wd:Q1)" in kin_query("Q1")
