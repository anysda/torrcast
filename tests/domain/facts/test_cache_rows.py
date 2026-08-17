"""Проверяет политику кэша справки: что значит ряд на диске и когда он протух."""

import time
from typing import Any

from torrcast.domain.facts.cache_rows import (
    _cached_facts,
    _fact_rows,
    _key,
    _origin_key,
    _origin_row,
    _row_origin,
)
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import EMPTY_TTL, SOURCE_MAP


def test_the_passport_rows_live_beside_the_blurbs_but_under_their_own_keys() -> None:
    """Один файл, но ряды разные: тип картины входит в ключ паспорта."""
    assert _key("Моана", 2016) == "Моана|2016"
    assert _key("Моана", None) == "Моана|"
    assert _origin_key("Моана", False) == "origin|movie|Моана"
    assert _origin_key("Моана", True) == "origin|tv|Моана"
    assert _origin_key("Моана", None) == "origin|either|Моана"


def test_a_passport_survives_the_round_trip_with_every_field_that_matters() -> None:
    """🔴 TC-450. Отметка источника и догадка обязаны доехать до второго показа."""
    paper = Origin(
        title="Serial Experiments Lain",
        year=1998,
        name="Эксперименты Лэйн",
        entity="Q1",
        guessed=True,
        namesake="9 (мультфильм, 2009)",
        source="wiki+map",
    )
    assert _row_origin(_origin_row(paper)) == paper


def test_a_row_written_before_the_source_mark_means_unknown_not_wikipedia() -> None:
    """Догадка вместо числа - та самая болезнь, от которой отметку и завели."""
    old: dict[str, Any] = {"title": "Dune", "year": 2021}
    found = _row_origin(old)
    assert found is not None
    assert (found.title, found.year, found.source) == ("Dune", 2021, "")
    assert _row_origin(None) is None, "ряда нет вовсе - значит не спрашивали"


def test_a_broken_row_is_the_same_as_no_row() -> None:
    """Битый кэш не роняет меню и не подсовывает мусор."""
    assert _cached_facts({"Моана|2016": "не словарь"}, [("Моана", 2016)], time.time()) == {}
    raw: dict[str, Any] = {"Моана|2016": {"rating": "IMDb 7.6"}}
    assert _cached_facts(raw, [("Моана", 2016)], time.time()) == {
        ("Моана", 2016): Fact(rating="IMDb 7.6")
    }


def test_a_stale_empty_answer_is_as_good_as_absent() -> None:
    """Срок у пустоты конечный: статью могли и написать - через :data:`EMPTY_TTL` спросим."""
    now = time.time()
    fresh: dict[str, Any] = {"Моана|2016": {"about": "", "rating": "", "runtime": "", "empty": now}}
    assert _cached_facts(fresh, [("Моана", 2016)], now) == {("Моана", 2016): Fact()}
    stale: dict[str, Any] = {
        "Моана|2016": {"about": "", "rating": "", "runtime": "", "empty": now - EMPTY_TTL - 1}
    }
    assert _cached_facts(stale, [("Моана", 2016)], now) == {}


def test_an_empty_row_without_an_expiry_is_asked_again() -> None:
    """Старый пустой ряд без срока не может навсегда закрыть поход к источнику."""
    raw: dict[str, Any] = {"Тачки|2006": {"about": "", "rating": "", "runtime": ""}}
    assert _cached_facts(raw, [("Тачки", 2006)], time.time()) == {}


def test_the_walk_writes_both_what_it_found_and_what_it_did_not() -> None:
    """Пустой ответ — тоже ответ, и он тоже помнится, только со сроком."""
    rows = _fact_rows({("Тачки", 2006): Fact(rating="IMDb 7.2")}, [("Моана", 2016)], 1000)
    assert rows["Тачки|2006"] == {"about": "", "rating": "IMDb 7.2", "runtime": ""}
    assert rows["Моана|2016"]["empty"] == 1000
    assert _fact_rows({}, [], 1000) == {}


def test_the_source_mark_is_counted_from_the_rows_on_disk() -> None:
    """🔴 TC-450. Польза карты - это число, а не вера: считают её по сохранённым рядам."""
    saved = {
        "Психо": Origin(title="Psycho", year=1960, source="wiki"),
        "Тачки": Origin(title="Cars", year=2006, source=SOURCE_MAP),
        "Эксперименты Лэйн": Origin(title="Serial Experiments Lain", source="wiki+map"),
    }
    read = {title: _row_origin(_origin_row(found)) for title, found in saved.items()}
    helped = [title for title, found in read.items() if found and SOURCE_MAP in found.source]
    assert sorted(helped) == ["Тачки", "Эксперименты Лэйн"]
