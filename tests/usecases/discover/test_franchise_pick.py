"""Зеркало :mod:`torrcast.usecases.discover.franchise_pick`: разбор имени с картой проводки."""

import pytest

from tests.fakes import composition
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.usecases.discover.franchise_pick import franchise_pick

_MAP = {
    "мы": [MapPicture("Мы", 2019, False, "Us", 399488)],
    "чем-мы-заняты-в-тени": [
        MapPicture("Чем мы заняты в тени", 2019, True, "What We Do in the Shadows", 129020)
    ],
}


def _picture(title: str, year: int, copies: int, kind: str = "movie") -> Picture:
    releases = [Release(raw_name=f"{title} {n}", title=title) for n in range(copies)]
    return Picture(title=title, year=year, kind=kind, releases=releases)  # type: ignore[arg-type]


_POOL = [
    _picture("Мы", 2019, 2),
    _picture("Чем мы заняты в тени", 2019, 2, "tv"),
    _picture("Чем мы заняты в тени", 2020, 2, "tv"),
]


def test_the_wired_map_keeps_a_short_name_on_its_own_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 «Мы» (Us, 2019): одна картина на две раздачи против двух сезонов соседа по слову."""
    composition.use_known_pictures(monkeypatch, lambda title: _MAP.get(slugify(title), []))

    assert [(p.title, p.year) for p in franchise_pick("Мы", _POOL)] == [("Мы", 2019)]


def test_without_the_map_the_pool_count_decides_as_before() -> None:
    """Карта молчит (тесты по умолчанию) - тощий тёзка уступает соседу, как уступал."""
    titles = {p.title for p in franchise_pick("Мы", _POOL)}

    assert titles == {"Чем мы заняты в тени"}


def test_an_uncontested_name_does_not_open_the_map(monkeypatch: pytest.MonkeyPatch) -> None:
    """Карта нужна лишь когда короткое имя спорит с более богатым соседом."""
    asked: list[str] = []

    def known(title: str) -> list[MapPicture]:
        asked.append(title)
        return []

    composition.use_known_pictures(monkeypatch, known)

    assert [picture.title for picture in franchise_pick("Мы", _POOL[:1])] == ["Мы"]
    assert asked == []
