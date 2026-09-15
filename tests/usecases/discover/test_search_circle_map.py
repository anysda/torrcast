"""Первый круг передаёт карту IMDb в выбор короткого имени."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.slugify import slugify
from torrcast.usecases.discover._search_state import _configure_recognize
from torrcast.usecases.discover.search_circle import search_circle

_MAP = {
    "мы": [MapPicture("Мы", 2019, False, "Us", 399488)],
    "чем-мы-заняты-в-тени": [
        MapPicture("Чем мы заняты в тени", 2019, True, "What We Do in the Shadows", 129020)
    ],
}
_POOL = [
    row("Мы / Us (2019) BDRip 1080p", "a"),
    row("Мы / Us (2019) WEB-DL 720p", "b"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2020) S02 WEB-DL 1080p", "c"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2020) S02 WEB-DL 720p", "d"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2024) S06 WEB-DL 1080p", "e"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2024) S06 WEB-DL 720p", "f"),
]


def _known(title: str) -> list[MapPicture]:
    return _MAP.get(slugify(title), [])


def test_the_first_circle_keeps_a_short_name_the_map_proves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Мы» (Us, 2019) не уступает двум сезонам соседа по слову."""
    wire_catalogue()
    composition.use_known_pictures(monkeypatch, _known)
    plans = search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["мы"]),
        Said(),
        indexer=lambda *_args: Indexer(answers={"мы": _POOL}),
    )

    assert plans[0].picture.title == "Мы"


def test_a_typo_the_indexers_do_not_know_finds_the_picture_by_its_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Интерстелар»: индексеры молчат по опечатке, карта знает картину и её имена."""
    wire_catalogue()
    composition.use_known_pictures(monkeypatch, _known)
    known = MapPicture("Интерстеллар", 2014, False, "Interstellar", 2605028)
    _configure_recognize(lambda _query, _wait: known)
    pool = [
        row("Интерстеллар / Interstellar (2014) BDRip 1080p", "a"),
        row("Interstellar.2014.2160p.UHD.BluRay.x265", "b"),
    ]
    indexer = Indexer(answers={"интерстеллар 2014": pool[:1], "interstellar 2014": pool[1:]})
    plans = search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["Интерстелар"]),
        Said(),
        indexer=lambda *_args: indexer,
    )

    assert (plans[0].picture.title, len(plans[0].picture.releases)) == ("Интерстеллар", 2)
    assert "Интерстелар" in indexer.asked
