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
from torrcast.usecases.choice.enter_take import enter_take
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
#: Что источник отдаёт на КОРОТКОЕ слово: сериал в выдаче есть, но рой у него мёртвый.
_SHORT_TALES = [
    row(
        "Тачки Мультачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2006) BDRip 1080p",
        "a",
        seeders=3,
    ),
    row("Тачки: Байки Мэтра / Mater's Tall Tales (2008) S01 WEB-DL 1080p", "b", seeders=1),
    row("Байки из склепа / Tales from the Crypt (1989) DVDRip", "c"),
]
#: Что источник отдаёт на ПОЛНОЕ имя: у сериала есть и живая раздача.
_FULL_TALES = [
    *_SHORT_TALES,
    row("Тачки: Байки Мэтра / Mater's Tall Tales (2008) S01 WEBRip 1080p", "d", seeders=400),
]
#: Источник, у которого короткое слово и полное имя отвечают РАЗНЫМ.
_TYPO_WORLD: dict[str, list[RawResult]] = {
    "байки метра": [],
    "байки": _SHORT_TALES,
    "метра": [],
    "байки мэтра": _FULL_TALES,
}


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


def _answer(query: str) -> str:
    """Что продукт отвечает на запрос: взятая картина и её вид, либо отказ."""
    try:
        plans, _client = _circle(_TYPO_WORLD, query)
    except NotFoundError:
        return "отказ"
    picture = plans[enter_take(plans, query).number - 1].picture
    return f"{picture.title}/{picture.kind}"


def test_a_typo_leads_to_the_same_picture_and_the_same_kind_as_the_clean_name() -> None:
    """🔴 TC-1004. Одна буква разницы уводила с сериала на одноимённый фильм.

    Ступень описки стояла ПОСЛЕДНЕЙ в круге поиска и отдавала готовый выбор картины -
    значит справка по оригиналу и все доборы, стоящие выше неё, на путь описки не
    попадали вовсе. Источник на короткое слово «байки» отдаёт сериал с мёртвым роем, на
    полное имя - с живым: клавиша, промахнувшаяся мимо «э», решала вид картины.

    Мера тут одна и она продуктовая: КАРТИНА и ВИД обязаны совпасть. Время совпадать не
    обязано - укороченный круг стоит своих секунд по замыслу.
    """
    assert _answer("байки метра") == _answer("байки мэтра") == "Тачки: Байки Мэтра/tv"


def test_the_corrected_name_is_asked_of_the_source_the_way_the_human_would_ask_it() -> None:
    """Исправленное имя уходит в источник: судьбу картины не решают по одному слову."""
    _plans, client = _circle(_TYPO_WORLD, "байки метра")

    assert "байки мэтра" in client.asked


def test_the_line_about_the_catalog_still_names_the_words_the_human_typed() -> None:
    """Строка про имя каталога называет НАБРАННОЕ, а не переписанную за человека строку."""
    wire_catalogue()
    said = Said()
    search_circle(
        _CONFIG,
        Args(query=["байки", "метра"]),
        said,
        indexer=lambda *_a, **_k: Indexer(answers=_TYPO_WORLD),
        passport=lambda *_a, **_k: Origin(),
    )

    assert "«байки метра» - в каталоге это «Тачки: Байки Мэтра»" in said.notes


def test_a_single_word_has_nothing_to_shorten() -> None:
    """Отбрасывать нечего - ветка молчит: короткие имена ею не ломаются."""
    assert _shorter("лёд") == []
    assert _shorter("дюна") == []


def test_the_shortest_word_goes_first_and_the_longest_second() -> None:
    """В коротком слове меньше всего смысла, в длинном - больше всего места для описки."""
    assert _shorter("байки метра") == ["байки", "метра"]
    assert _shorter("пираты карибского моря") == ["пираты карибского", "пираты моря"]


#: Источник, у которого второй вопрос ПЕРЕПИСЫВАЕТ имя уже найденной раздачи.
#: Склейка выбирает имя раздачи большинством по одному ``infoHash`` (:func:`merge`), и
#: строка покороче забирает ничью, - имя каталога после слияния пропадает из кластера.
_RENAMING_WORLD: dict[str, list[RawResult]] = {
    "байки метра": [],
    "байки": [
        row("Байки Мэтра / Mater's Tall Tales (2008) S01 WEB-DL 1080p", "a"),
        row("Байки из склепа / Tales from the Crypt (1989) DVDRip", "b"),
    ],
    "байки мэтра": [row("Призрак / Ghost (2008) S01 WEB-DL 1080p", "a")],
    "метра": [],
}


def test_a_second_ask_that_renames_the_release_does_not_stop_the_search() -> None:
    """Пустой ответ ПОСЛЕ слияния ведёт к следующему кандидату, а не к выходу из круга.

    Второй вопрос приносит ту же раздачу под другим именем, склейка берёт имя
    большинством (:func:`~torrcast.adapters.prowlarr.merge.merge`), и опознанное имя
    каталога из пересобранного кластера пропадает. Оборвись перебор на этом - второе
    укороченное слово источник бы уже не увидел, хотя прежний круг его спрашивал.
    """
    with pytest.raises(NotFoundError):
        _circle(_RENAMING_WORLD, "байки метра")


def test_the_renaming_second_ask_leaves_the_next_shortened_word_asked() -> None:
    """Тот же расклад мерой источника: второе укороченное слово обязано быть спрошено."""
    client = Indexer(answers=_RENAMING_WORLD)
    wire_catalogue()
    with pytest.raises(NotFoundError):
        search_circle(
            _CONFIG,
            Args(query=["байки", "метра"]),
            Said(),
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    assert "метра" in client.asked, "перебор кандидатов оборвался на первом же слове"
