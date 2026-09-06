"""Зеркало :mod:`torrcast.domain.facts.kin_query`: строка SPARQL за родней картины."""

from torrcast.domain.facts.kin_query import kin_query


def test_both_series_and_chain_properties_are_asked_in_one_query() -> None:
    """Оба свойства едут одним походом: у части франшиз нет общего элемента серии."""
    query = kin_query("Q105598")

    assert "wd:Q105598 wdt:P179" in query
    assert "wd:Q105598 (wdt:P155|wdt:P156)*" in query
    assert query.count("wd:Q105598") == 3, "картина упомянута в серии, цепочке и фильтре"


def test_the_asked_picture_is_filtered_out_of_its_own_kin() -> None:
    """P155/P156 со звёздочкой на нулевом шаге возвращает саму картину - её вычёркивает FILTER."""
    assert "FILTER(?item != wd:Q1)" in kin_query("Q1")
