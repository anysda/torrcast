"""Зеркало упреждающей справки: её спрашивают вместе с первым кругом, а не после него."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from tests import thread_guard
from tests.fakes.article_source import FakeArticleSource
from tests.fakes.date_source import FakeDateSource
from tests.fakes.name_catalogue import FakeNameCatalogue
from tests.fakes.origin_store import FakeOriginStore
from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.domain.raw_result import RawResult
from torrcast.usecases.discover._passport_ahead import _passport_ahead
from torrcast.usecases.discover.search_circle import search_circle
from torrcast.usecases.passport import Passport


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русский круг поиска."""


_CARS = [row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66)]


class _Hearing(Indexer):
    """Индексер, который отвечает, только дав справке время себя спросить."""

    def __init__(self, asked: threading.Event, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._asked = asked
        self.heard: list[bool] = []

    def search(self, query: str) -> list[RawResult]:
        self.heard.append(self._asked.wait(2.0))
        return super().search(query)


def test_the_passport_is_asked_while_the_first_circle_is_still_searching() -> None:
    """Справку спросили раньше, чем индексеры ответили, и тем же именем, что ищет круг."""
    wire_catalogue()
    asked = threading.Event()
    names: list[tuple[str, bool | None]] = []

    def passport(name: str, series: bool | None = False, **_kwargs: Any) -> Origin:
        names.append((name, series))
        asked.set()
        return Origin()

    client = _Hearing(asked, answers={"тачки": _CARS})
    search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["тачки"]),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=passport,
    )

    assert client.heard[0], "первый круг ответил, а справку так и не спросили"
    assert names[0] == ("тачки", None)


def test_the_ask_after_the_circle_waits_for_the_lookup_begun_with_it() -> None:
    """Вопрос после круга не идёт в Википедию заново, а ждёт уже идущий поход."""
    release = threading.Event()
    begun = {False: threading.Event(), True: threading.Event()}

    def article(title: str, series: bool, timeout: float) -> Origin:
        begun[series].set()
        release.wait(5.0)
        return Origin(title="Ghost in the Shell", name=title) if not series else Origin()

    articles = FakeArticleSource(article)
    passport = Passport(articles, FakeNameCatalogue(), FakeOriginStore(), FakeDateSource())

    before = thread_guard.alive()
    _passport_ahead(passport.of, "Призрак в доспехах")
    assert begun[False].wait(2.0) and begun[True].wait(2.0), (
        "справку не начали спрашивать до конца круга"
    )

    early = passport.of("Призрак в доспехах", False, 0.0)
    assert len(articles.calls) == 2, "вопрос после круга пошёл в сеть второй раз"
    release.set()
    got = passport.of("Призрак в доспехах", False, 2.0)
    for thread in thread_guard.alive() - before:
        thread.join(5.0)

    assert not early.title, "по нулевому сроку ответа ещё нет"
    assert got.title == "Ghost in the Shell", "поздний вопрос не дождался начатого похода"
    assert len(articles.calls) == 2, "вопрос после круга пошёл в сеть второй раз"
