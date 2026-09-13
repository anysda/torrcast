"""Заказ плиток полки: сведения раньше круга, родня своей картины после него."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.facts import FactPicture
from torrcast.usecases.select.plan import Plan
from web.warm_targets import WarmTargets


def _plan(title: str, year: int) -> Plan:
    picture = Picture(title=title, year=year, kind="movie")
    picture.releases = [Release(raw_name=f"{title} {year} BDRip", title=title)]
    return Plan(picture=picture, ranked=list(picture.releases), runtime=8520.0, warn_mbit=12.0)


_OTHER = _plan("Interstellar", 2014)
_OWN = _plan("Побег из Шоушенка", 1994)


def test_a_shelf_target_starts_the_related_shelf_of_its_own_picture() -> None:
    """Круг поиска может поставить плитку не первой, но родня остаётся её."""
    related: list[FactPicture] = []
    targets = WarmTargets(
        circle=lambda _query: [_OTHER, _OWN], prime=lambda _p: None, kin=related.append
    )

    targets.prepare(
        [("The Shawshank Redemption", _OWN.picture.key, "Побег из Шоушенка", 1994, "movie")]
    )
    targets.search("The Shawshank Redemption")

    assert related == [("Побег из Шоушенка", 1994, "movie")]


def test_an_unordered_circle_starts_the_related_shelf_of_its_first_picture() -> None:
    """Живой круг без заказа полки заводит родню первой картины, как карточка."""
    related: list[FactPicture] = []
    targets = WarmTargets(
        circle=lambda _query: [_OWN, _OTHER], prime=lambda _p: None, kin=related.append
    )

    targets.search("Шоушенк")

    assert related == [("Побег из Шоушенка", 1994, "movie")]


def test_an_empty_circle_starts_no_related_shelf() -> None:
    """Пустая находка родни не заводит: картины нет."""
    related: list[FactPicture] = []
    targets = WarmTargets(circle=lambda _query: [], prime=lambda _p: None, kin=related.append)

    assert targets.search("ничего") == []
    assert related == []


def test_a_shelf_primes_facts_before_it_queues_its_indexer_circle() -> None:
    """Сведения плитки готовы раньше, чем круг раздач хотя бы поставлен в очередь."""
    order: list[str] = []

    def ask(screen: Sequence[str]) -> int:
        order.append(f"ask {list(screen)}")
        return len(screen)

    targets = WarmTargets(
        circle=lambda _query: [],
        prime=lambda pictures: order.append(f"prime {pictures}"),
        kin=lambda _picture: None,
        ask=ask,
    )

    assert (
        targets.prepare([("Interstellar", _OTHER.picture.key, "Interstellar", 2014, "movie")]) == 1
    )
    assert order == ["prime [('Interstellar', 2014, 'movie')]", "ask ['Interstellar']"]


def test_an_observed_tile_primes_in_the_background_before_its_circle() -> None:
    """`seen` не держит браузер за Wikipedia, но начинает её до клика."""
    order: list[str] = []
    jobs: list[Callable[[], None]] = []

    def ask(queries: Sequence[str]) -> int:
        order.append(f"ask {list(queries)}")
        return 1

    targets = WarmTargets(
        circle=lambda _query: [], prime=lambda pictures: order.append(f"prime {pictures}"),
        kin=lambda _picture: None, ask=ask, spawn=jobs.append,
    )

    assert targets.observe([("Luca", "movie:luca:2021", "Лука", 2021, "movie")]) == 1
    assert order == ["ask ['Luca']"]
    jobs.pop()()
    assert order == ["ask ['Luca']", "prime [('Лука', 2021, 'movie')]"]
