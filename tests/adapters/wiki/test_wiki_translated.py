"""Проверяет справку на языке продукта: адрес статьи, три исхода разбора и след."""

from __future__ import annotations

from typing import Any

from tests.fakes.journal import Tape
from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.endpoints import WIKI_HOST
from torrcast.adapters.wiki.wiki_translated import wiki_translated
from torrcast.domain.catalogs.tongue import EN
from torrcast.domain.facts.blurb_outcome import ABSENT, BLANK, PARSED

UTENA_KEY = ("Юная революционерка Утэна", 1997)
#: Первая фраза той же статьи в английской Википедии - ровно то, ради чего вторая волна.
UTENA_EN = (
    "Revolutionary Girl Utena is a Japanese anime television series directed by "
    "Kunihiko Ikuhara and produced by J.C.Staff."
)
LINK = "Revolutionary Girl Utena"


def _pages(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"query": {"pages": list(rows)}}


def _answers(**articles: str) -> FakeJsonClient:
    """Клиент, отвечающий английскими статьями по заголовку; чужой хост молчит пустотой."""
    found = {name.replace("_", " "): text for name, text in articles.items()}

    def answer(host: str, path: str, params: dict[str, str]) -> Any:
        asked = params["titles"].split("|")
        return _pages(*({"title": name, "extract": found[name]} for name in asked if name in found))

    return FakeJsonClient(answer=answer)


def test_the_english_product_reads_the_blurb_from_the_english_source(_english: None) -> None:
    """Под английским языком зритель читает английскую статью, а не русскую."""
    client = _answers(Revolutionary_Girl_Utena=UTENA_EN)
    spoken, outcome = wiki_translated(client, [UTENA_KEY], {UTENA_KEY: LINK}, EN, 0.5)
    assert spoken == {UTENA_KEY: UTENA_EN}
    assert outcome == {UTENA_KEY: PARSED}


def test_the_wave_goes_by_the_link_and_not_by_the_russian_name(_english: None) -> None:
    """Английская Википедия про «Юную революционерку Утэну» не знает: спрашивают ссылкой."""
    client = _answers(Revolutionary_Girl_Utena=UTENA_EN)
    wiki_translated(client, [UTENA_KEY], {UTENA_KEY: LINK}, EN, 0.5)
    hosts = {host for host, _path, _params in client.calls}
    asked = [params["titles"] for _host, _path, params in client.calls]
    assert hosts == {"en.wikipedia.org"}
    assert WIKI_HOST not in hosts
    assert asked == [LINK]


def test_a_picture_without_a_link_loses_the_blurb_instead_of_borrowing_a_foreign_one(
    _english: None,
) -> None:
    """🔴 Статьи на этом языке нет - справки нет вовсе: подменять её русской нельзя."""
    client = _answers()
    spoken, outcome = wiki_translated(client, [UTENA_KEY], {}, EN, 0.5)
    assert spoken == {}
    assert outcome == {UTENA_KEY: ABSENT}
    assert client.calls == []


def test_a_named_article_that_gave_nothing_is_a_defect_and_not_an_absence(_english: None) -> None:
    """Ссылка есть, а описания нет - это дефект, и от «нет статьи» он отличается словом."""
    client = _answers()
    _spoken, outcome = wiki_translated(client, [UTENA_KEY], {UTENA_KEY: LINK}, EN, 0.5)
    assert outcome == {UTENA_KEY: BLANK}


def test_the_trace_counts_the_three_outcomes_apart(_english: None, tape: Tape) -> None:
    """🔴 Доля пропавшей справки считается только по РАЗЛИЧИМЫМ исходам; вот они тремя."""
    parsed, absent, blank = UTENA_KEY, ("Тачки", 2006), ("Моана", 2016)
    client = _answers(Revolutionary_Girl_Utena=UTENA_EN)
    wiki_translated(
        client,
        [parsed, absent, blank],
        {parsed: LINK, blank: "Moana (2016 film)"},
        EN,
        0.5,
    )
    said = tape.named("справка: язык продукта")[0]
    assert (said["разобрано"], said["нет_статьи"], said["пусто"]) == (1, 1, 1)
    assert said["пустые"] == ["Моана"]
    assert said["язык"] == EN


def test_nothing_at_all_is_traced_when_there_was_nothing_to_translate(
    _english: None, tape: Tape
) -> None:
    """Пустое событие в следе - шум: считать по нему нечего, а искать глазами мешает."""
    wiki_translated(_answers(), [], {}, EN, 0.5)
    assert tape.named("справка: язык продукта") == []
