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
from torrcast.domain.facts.settings import EMPTY_TTL, FACTS_RULES, SOURCE_MAP
from torrcast.domain.json_map import json_map


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
    raw: dict[str, Any] = {"Моана|2016": {"rating": "IMDb 7.6", "rules": FACTS_RULES}}
    assert _cached_facts(raw, [("Моана", 2016)], time.time()) == {
        ("Моана", 2016): Fact(rating="IMDb 7.6")
    }


def test_a_row_judged_by_previous_rules_is_judged_again() -> None:
    """🔴 TC-843. Полка живёт дольше правил: починка разбора обязана доехать до зрителя.

    И отказ, и находка прежнего номера пересуживаются - за ними идут в сеть, а не берут
    на веру; ряд кода, который номера ещё не писал, - тоже ряд прежних правил.
    """
    now = time.time()
    found: dict[str, Any] = {
        "Моана|2016": {"about": "о дочери вождя", "rating": "IMDb 7.6", "rules": FACTS_RULES - 1}
    }
    assert _cached_facts(found, [("Моана", 2016)], now) == {}
    refused: dict[str, Any] = {
        "Тачки|2006": {"about": "", "rating": "", "runtime": "", "empty": now, "rules": 0}
    }
    assert _cached_facts(refused, [("Тачки", 2006)], now) == {}
    unmarked: dict[str, Any] = {"Дюна|2021": {"about": "о пустыне", "rating": "IMDb 8.0"}}
    assert _cached_facts(unmarked, [("Дюна", 2021)], now) == {}


def test_a_row_judged_by_current_rules_is_taken_without_a_walk() -> None:
    """Ряд нынешнего номера лежит как лежал: пересуд без смены правил стоил бы сети."""
    now = time.time()
    raw: dict[str, Any] = {
        "Моана|2016": {"about": "о дочери вождя", "rating": "IMDb 7.6", "rules": FACTS_RULES},
        "Тачки|2006": {
            "about": "",
            "rating": "",
            "runtime": "",
            "empty": now,
            "rules": FACTS_RULES,
        },
    }
    assert _cached_facts(raw, [("Моана", 2016), ("Тачки", 2006)], now) == {
        ("Моана", 2016): Fact(about="о дочери вождя", rating="IMDb 7.6"),
        ("Тачки", 2006): Fact(),
    }


def test_a_stale_empty_answer_is_as_good_as_absent() -> None:
    """Срок у пустоты конечный: статью могли и написать - через :data:`EMPTY_TTL` спросим."""
    now = time.time()
    fresh: dict[str, Any] = {
        "Моана|2016": {"about": "", "rating": "", "runtime": "", "empty": now, "rules": FACTS_RULES}
    }
    assert _cached_facts(fresh, [("Моана", 2016)], now) == {("Моана", 2016): Fact()}
    stale: dict[str, Any] = {
        "Моана|2016": {
            "about": "",
            "rating": "",
            "runtime": "",
            "empty": now - EMPTY_TTL - 1,
            "rules": FACTS_RULES,
        }
    }
    assert _cached_facts(stale, [("Моана", 2016)], now) == {}


def test_an_empty_row_without_an_expiry_is_asked_again() -> None:
    """Старый пустой ряд без срока не может навсегда закрыть поход к источнику."""
    raw: dict[str, Any] = {
        "Тачки|2006": {"about": "", "rating": "", "runtime": "", "rules": FACTS_RULES}
    }
    assert _cached_facts(raw, [("Тачки", 2006)], time.time()) == {}


def test_the_walk_writes_both_what_it_found_and_what_it_did_not() -> None:
    """Пустой ответ — тоже ответ, и он тоже помнится, только со сроком."""
    rows = _fact_rows({("Тачки", 2006): Fact(rating="IMDb 7.2")}, [("Моана", 2016)], 1000)
    assert rows["Тачки|2006"] == {
        "about": "",
        "rating": "IMDb 7.2",
        "runtime": "",
        "rules": FACTS_RULES,
    }
    miss = json_map(rows["Моана|2016"])
    assert (miss["empty"], miss["rules"]) == (1000, FACTS_RULES)
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


def test_an_impossible_running_time_is_dropped_off_a_row_that_never_expires() -> None:
    """У найденного ряда срока нет, и записанная однажды выдумка печаталась бы вечно."""
    raw: dict[str, Any] = {
        "Оппенгеймер|2023": {
            "about": "о физике",
            "rating": "IMDb 8.3",
            "runtime": "180 ч 9 мин",
            "rules": FACTS_RULES,
        }
    }
    assert _cached_facts(raw, [("Оппенгеймер", 2023)], time.time()) == {
        ("Оппенгеймер", 2023): Fact(about="о физике", rating="IMDb 8.3")
    }


def test_a_believable_running_time_stays_on_the_row() -> None:
    """Граница режет выдумку, а не хронометраж: три часа с ряда снимать нечего."""
    raw: dict[str, Any] = {"Оппенгеймер|2023": {"runtime": "3 ч", "rules": FACTS_RULES}}
    assert _cached_facts(raw, [("Оппенгеймер", 2023)], time.time()) == {
        ("Оппенгеймер", 2023): Fact(runtime="3 ч")
    }


def test_the_russian_shelf_keeps_the_key_it_always_had() -> None:
    """🔴 Сдвинь ключ русского ряда - и всё накопленное у людей разом станет промахом."""
    assert _key("Тачки", 2006) == "Тачки|2006"
    assert _key("Тачки", None) == "Тачки|"
    assert _key("Тачки", 2006, "ru") == "Тачки|2006"


def test_each_language_gets_its_own_shelf() -> None:
    """Описания у языков разные: в одном ряду они затирали бы друг друга через прогон."""
    assert _key("Тачки", 2006, "en") != _key("Тачки", 2006)


def test_a_russian_row_is_not_read_as_an_english_one() -> None:
    """Иначе под --en с полки поднималось бы русское описание - и без всякой сети."""
    raw: dict[str, Any] = {_key("Тачки", 2006): {"about": "русское описание", "rules": FACTS_RULES}}
    assert _cached_facts(raw, [("Тачки", 2006)], time.time(), "en") == {}
    assert _cached_facts(raw, [("Тачки", 2006)], time.time())[("Тачки", 2006)].about == (
        "русское описание"
    )


def test_an_english_walk_writes_to_the_english_shelf() -> None:
    """Записанное под чужим языком не вправе подменить русский ряд на диске."""
    rows = _fact_rows({("Тачки", 2006): Fact(about="an english blurb")}, [], 0, "en")
    assert list(rows) == [_key("Тачки", 2006, "en")]
