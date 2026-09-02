"""Зеркало круга на описку: запрос короче на слово, а имя каталога сверяется целиком."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.goal_spare import GOAL
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._second_typo import _shorter
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.select.plan import Plan


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русский запрос с опиской и русская же строка отказа."""


_CONFIG = Config(prowlarr_apikey="KEY")
#: Выдача источника по одному слову «байки»: та самая картина и два чужих однословца.
_TALL_TALES = [
    row("Тачки Мультачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2006) BDRip 1080p", "a"),
    row("Байки из склепа / Tales from the Crypt (1989) DVDRip", "b"),
    row("Байки Мидгарда / Tales of Midgard (2018) WEBRip 1080p", "c"),
]
#: Выдача по слову «унесенные»: имя картины ВХОДИТ в запрос, но картина другая.
_SWEPT_AWAY = [row("Унесенные / Swept Away (2002) BDRip 1080p", "a")]


def _circle(answers: dict[str, list[RawResult]], query: str) -> tuple[list[Plan], Indexer]:
    wire_catalogue()
    client = Indexer(answers=answers)
    plans = search_circle(
        _CONFIG,
        Args(query=query.split()),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: Origin(),
    )
    return plans, client


def test_a_letter_missed_in_one_word_reaches_the_picture_instead_of_the_refusal() -> None:
    """🔴 TC-986. «байки метра» источник не находит вовсе, а «байки» находит - и там Мэтр.

    Прощение написания у каталога есть давно, но живого материала ему не давали: круг
    спрашивали дословно и один раз.
    """
    plans, client = _circle({"байки": _TALL_TALES}, "байки метра")

    assert [plan.picture.title for plan in plans] == ["Тачки Мультачки: Байки Мэтра"]
    assert "байки" in client.asked, "укороченным запросом источник так и не спросили"


def test_the_shortened_circle_is_asked_with_the_floor_of_the_top_up() -> None:
    """⚠️ Пол бюджета круга берётся у добора (TC-386), своего эта ветка не заводит."""
    _plans, client = _circle({"байки": _TALL_TALES}, "байки метра")

    assert client.floors[client.asked.index("байки")] == GOAL


def test_a_name_that_merely_enters_the_query_does_not_become_the_picture() -> None:
    """🔴 Широкий запрос не вправе подменить картину: «Унесенные» это не «Унесённые призраками».

    Отбор на широком пуле цепляется за имя, всего лишь ВХОДЯЩЕЕ в запрос, и человек молча
    получал бы не ту картину. Ворота тут одни - имя, отличающееся от ВСЕГО запроса одной
    буквой; не нашлось - отказ остаётся прежним, слово в слово.
    """
    with pytest.raises(NotFoundError) as refusal:
        _circle({"унесенные": _SWEPT_AWAY}, "унесённые призракоми")

    assert "ничего не нашлось" in str(refusal.value)


def test_a_query_answered_by_the_first_circle_never_pays_for_the_shortened_one() -> None:
    """Запрос, нашедшийся сразу, укороченного круга не видит и не платит за него."""
    _plans, client = _circle({"байки мэтра": _TALL_TALES}, "байки мэтра")

    assert "байки" not in client.asked
    assert "мэтра" not in client.asked


def test_a_single_word_has_nothing_to_shorten() -> None:
    """Отбрасывать нечего - ветка молчит: короткие имена ею не ломаются."""
    assert _shorter("лёд") == []
    assert _shorter("дюна") == []


def test_the_shortest_word_goes_first_and_the_longest_second() -> None:
    """В коротком слове меньше всего смысла, в длинном - больше всего места для описки."""
    assert _shorter("байки метра") == ["байки", "метра"]
    assert _shorter("пираты карибского моря") == ["пираты карибского", "пираты моря"]
