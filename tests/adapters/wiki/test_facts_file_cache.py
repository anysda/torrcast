"""Проверяет кэш справки и паспортов поверх одного JSON-хранилища."""

import json
from pathlib import Path

from tests.fakes.json_store import FakeJsonStore
from torrcast.adapters.wiki.facts_file_cache import FactsFileCache
from torrcast.adapters.wiki.json_file_store import JsonFileStore
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import EMPTY_TTL, SOURCE_WIKI


def test_a_passport_is_written_once_and_read_back_under_its_own_type() -> None:
    """Внутренние пробы фильма и сериала не становятся ответами на запрос с типом."""
    cache = FactsFileCache(FakeJsonStore())
    found = Origin(title="Serial Experiments Lain", year=1998, source=SOURCE_WIKI)

    assert cache.read("Эксперименты Лэйн", None) is None
    cache.write("Эксперименты Лэйн", None, found)

    assert cache.read("Эксперименты Лэйн", None) == found
    assert cache.read("Эксперименты Лэйн", False) is None
    assert cache.read("Эксперименты Лэйн", True) is None


def test_broken_cache_is_the_same_as_no_cache(tmp_path: Path) -> None:
    """Битый кэш не роняет меню и не подсовывает мусор."""
    path = tmp_path / "facts.json"
    path.write_text("{не json", encoding="utf-8")
    cache = FactsFileCache(JsonFileStore(path))

    assert cache.blurbs([("Моана", 2016)]) == {}

    path.write_text(json.dumps({"Моана|2016": {"rating": "IMDb 7.6"}}), encoding="utf-8")
    assert cache.blurbs([("Моана", 2016)]) == {("Моана", 2016): Fact(rating="IMDb 7.6")}


def test_an_empty_answer_is_remembered_with_an_expiry() -> None:
    """Пустой ответ - тоже ответ, и в сеть за ним больше не идут, пока не вышел срок."""
    store = FakeJsonStore()
    now = 1_000_000.0
    cache = FactsFileCache(store, lambda: now)
    cache.remember({("Тачки", 2006): Fact(rating="IMDb 7.2")}, [("Моана", 2016)])

    assert cache.blurbs([("Тачки", 2006), ("Моана", 2016)]) == {
        ("Тачки", 2006): Fact(rating="IMDb 7.2"),
        ("Моана", 2016): Fact(),
    }

    stale = FactsFileCache(store, lambda: now + EMPTY_TTL + 1)
    assert stale.blurbs([("Моана", 2016)]) == {}, "срок вышел - ряда как не было"
    assert stale.blurbs([("Тачки", 2006)]), "у найденной справки срока нет"


def test_nothing_to_remember_never_touches_the_store() -> None:
    """Ни находки, ни опровержения - и хранилище не переписывается впустую."""
    store = FakeJsonStore()
    FactsFileCache(store).remember({}, [])

    assert store.writes == 0
