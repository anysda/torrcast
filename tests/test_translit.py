"""Русское название, а раздачи подписаны латиницей: второй заход поиска.

Половина каталога подписана только на латинице («Psycho.1960.1080p»), и русский
запрос до неё не достаёт: индексер ищет по имени раздачи. Здесь проверяется, что
torrcast сам догадывается переспросить, что берёт название из первой же выдачи и
что на полной выдаче второго запроса не случается вовсе.
"""

from __future__ import annotations

import io
from typing import Any

import pytest

from torrcast import NotFoundError, cli
from torrcast.console import Progress
from torrcast.parse import THIN_POOL, Release, alt_query, parse_release_name, transliterate
from torrcast.search import RawResult, merge
from torrcast.state import Config

GB = 1024**3


def raw(name: str, number: int, seeders: int = 100) -> RawResult:
    """Строка выдачи: hash различает раздачи, по нему же они и склеиваются."""
    return RawResult(
        title=name, info_hash=f"{number:040x}", size=int(8 * GB), seeders=seeders, indexer="Knaben"
    )


def ru(name: str) -> Release:
    return parse_release_name(name)


def test_transliterate_writes_russian_title_in_latin() -> None:
    assert transliterate("Брат") == "brat"
    assert transliterate("Ёлки") == "elki"
    assert transliterate("Щука") == "shchuka"
    assert transliterate("Иван Васильевич") == "ivan vasilevich"


def test_transliterate_keeps_latin_and_digits() -> None:
    assert transliterate("Матрица 2") == "matritsa 2"
    assert transliterate("The Matrix") == "the matrix"


def test_alt_query_takes_original_title_from_the_thin_results() -> None:
    """Оригинал из выдачи точнее транслита: «Психо» → Psycho, а не psikho."""
    thin = [ru("Психо / Psycho (1960) BDRip 1080p"), ru("Психо / Psycho (1960) DVDRip")]
    assert alt_query("психо", thin) == "Psycho"


def test_alt_query_prefers_the_most_common_original() -> None:
    pool = [
        ru("Сияние / The Shining (1980) BDRip 1080p"),
        ru("Сияние / The Shining (1980) DVDRip"),
        ru("Сияние / Shine (1996) DVDRip"),
    ]
    assert alt_query("сияние", pool) == "The Shining"


def test_alt_query_ignores_originals_of_other_pictures() -> None:
    """В выдаче по «психо» лежит и «Идентификация», её оригинал брать нельзя."""
    pool = [
        ru("Идентификация / Identity (2003) BDRip"),
        ru("Психо / Psycho (1960) DVDRip"),
    ]
    assert alt_query("психо", pool) == "Psycho"


def test_alt_query_falls_back_to_translit_when_nothing_was_found() -> None:
    """Выдачи нет вовсе - читать оригинал неоткуда, остаётся транслит."""
    assert alt_query("брат", []) == "brat"


def test_alt_query_is_empty_for_a_latin_request() -> None:
    """Спросили латиницей - добирать нечем, второго захода не бывает."""
    assert alt_query("psycho", [ru("Психо / Psycho (1960) DVDRip")]) == ""


def test_merge_keeps_each_torrent_once_and_holds_the_order() -> None:
    first, second = [raw("Психо", 1), raw("Психо", 2)], [raw("Psycho", 2), raw("Psycho", 3)]
    merged = merge(first, second)
    assert [r.title for r in merged] == ["Психо", "Психо", "Psycho"]


class _FakeProwlarr:
    """Индексер, который русский запрос знает хуже латинского - как живой."""

    def __init__(self, catalog: dict[str, list[RawResult]]) -> None:
        self.catalog = catalog
        self.asked: list[str] = []

    def __call__(self, url: str, apikey: str) -> _FakeProwlarr:
        return self

    def search(self, query: str, limit: int = 100) -> list[RawResult]:
        self.asked.append(query)
        found = self.catalog.get(query.casefold(), [])
        if not found:
            raise NotFoundError(f"по запросу «{query}» ничего не нашлось")
        return found


def _catalog(russian: int, latin: int) -> _FakeProwlarr:
    """«Психо»: по-русски пара DVDRip'ов, на латинице - весь каталог в 1080p."""
    return _FakeProwlarr(
        {
            "психо": [raw(f"Психо / Psycho (1960) DVDRip {i}", i) for i in range(russian)],
            "psycho": [
                raw(f"Psycho.1960.1080p.BluRay.x264-GRP{i}", 100 + i) for i in range(latin)
            ],
        }
    )


def _search(
    client: _FakeProwlarr, query: str, monkeypatch: pytest.MonkeyPatch
) -> tuple[Any, str]:
    """План поиска и всё, что он сказал вслух."""
    monkeypatch.setattr(cli, "Prowlarr", client)
    config = Config(tv="127.0.0.1", prowlarr_apikey="KEY")
    args = cli.Args(query=query.split())
    out = io.StringIO()
    with Progress(out=out) as progress:
        return cli._search(config, args, progress), out.getvalue()


def test_thin_russian_pool_is_topped_up_by_the_latin_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Два русских DVDRip'а - повод переспросить: рядом лежит сорок 1080p."""
    client = _catalog(russian=2, latin=40)
    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 42
    assert "по-русски раздач 2 - добрал по «Psycho»: стало 42" in said


def test_full_russian_pool_is_not_searched_twice(monkeypatch: pytest.MonkeyPatch) -> None:
    """Счастливый путь не платит за чужую беду: полная выдача - один запрос."""
    client = _catalog(russian=THIN_POOL, latin=40)
    plans, _said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо"]
    assert len(plans[0].picture.releases) == THIN_POOL


def test_nothing_found_in_russian_is_searched_by_translit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Пустая выдача - тот же случай: читать оригинал неоткуда, идём транслитом."""
    client = _FakeProwlarr({"brat": [raw(f"Brat.1997.BDRip.x264-{i}", i) for i in range(20)]})
    plans, _said = _search(client, "брат", monkeypatch)

    assert client.asked == ["брат", "brat"]
    assert len(plans[0].picture.releases) == 20


def test_second_search_that_found_nothing_leaves_the_first_result_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Добор - не обещание: не нашлось ничего нового, играем то, что было, и молчим."""
    client = _catalog(russian=3, latin=0)
    plans, said = _search(client, "психо", monkeypatch)

    assert client.asked == ["психо", "Psycho"]
    assert len(plans[0].picture.releases) == 3
    assert "добрал" not in said


def test_nothing_anywhere_is_still_an_honest_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeProwlarr({})
    with pytest.raises(NotFoundError, match="ничего не нашлось"):
        _search(client, "нетакогофильма", monkeypatch)
