"""Проверяет проводку справки: один клиент, один кэш и оба её сценария."""

from pathlib import Path

from torrcast.adapters.wiki.facts_file_cache import FactsFileCache
from torrcast.adapters.wiki.imdb_names import ImdbNames
from torrcast.adapters.wiki.wiki_articles import WikiArticles
from torrcast.adapters.wiki.wiki_blurbs import WikiBlurbs
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import USER_AGENT
from torrcast.runtime.facts_wiring import FACTS, FactsWiring
from torrcast.usecases.passport import Passport


def test_the_process_gets_one_assembled_reference() -> None:
    """Единственное место, где сценарии справки видят свои адаптеры, - эта проводка."""
    assert isinstance(FACTS, FactsWiring)
    assert isinstance(FACTS.passport, Passport)
    assert isinstance(FACTS.articles, WikiArticles)
    assert isinstance(FACTS.blurbs, WikiBlurbs)
    assert isinstance(FACTS.catalogue, ImdbNames)
    assert isinstance(FACTS.cache, FactsFileCache)


def test_one_client_and_one_catalogue_serve_every_step(tmp_path: Path) -> None:
    """Память адресов и разобранные выгрузки терять между вызовами незачем."""
    wiring = FactsWiring(lambda: tmp_path / "facts.json")

    assert wiring.client.user_agent == USER_AGENT
    assert wiring.articles.client is wiring.client
    assert wiring.blurbs.client is wiring.client
    assert wiring.articles.catalogue is wiring.catalogue
    assert isinstance(wiring.catalogue, ImdbNames)
    assert wiring.catalogue.ratings is wiring.ratings
    assert wiring.passport.store is wiring.cache


def test_different_state_directories_do_not_read_each_others_cache(tmp_path: Path) -> None:
    """Разные каталоги состояния не читают и не дописывают кэш друг друга."""
    first = tmp_path / "first" / "facts.json"
    second = tmp_path / "second" / "facts.json"
    where = first
    wiring = FactsWiring(lambda: where)

    wiring.cache.remember({("Тачки", 2006): Fact(rating="IMDb 7.2")})
    wiring.cache.write("Тачки", False, Origin(title="Cars", year=2006))
    assert wiring.cache.blurbs([("Тачки", 2006)])
    assert first.exists()

    where = second
    assert wiring.cache.blurbs([("Тачки", 2006)]) == {}
    assert wiring.cache.read("Тачки", False) is None
    assert not second.exists()
