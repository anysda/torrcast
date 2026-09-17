"""ShelfPlayable: приговор плитки «играет» - фоном, и запоминается под правило отбора."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.shelf_playable import ShelfPlayable

_RELEASE = Release(raw_name="Film 2010 BDRip 1080p LostFilm", title="Film", magnet="magnet:f")
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_RELEASE])
_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE], runtime=0, warn_mbit=0)
_CONFIG = Config(torrserver_url="http://ts", receiver_profile="q70d")


@dataclass
class _Voices:
    """Подмена отбора дорожек: отвечает названным приговором и считает свои вызовы."""

    heard: Any
    calls: list[str] = field(default_factory=list)

    def __call__(self, plan: Plan, query: str, config: Config) -> tuple[Any, bool]:
        self.calls.append(query)
        return self.heard, False


def _circle(plans: list[Plan]) -> Any:
    return lambda _query: plans


def test_a_found_release_makes_the_tile_playable() -> None:
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=_Voices(heard=object()))

    assert playable.of("film", _PICTURE.key, _CONFIG) is True


def test_no_heard_release_makes_the_tile_not_playable() -> None:
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=_Voices(heard=None))

    assert playable.of("film", _PICTURE.key, _CONFIG) is False


def test_a_key_missing_from_the_circle_is_not_playable_and_never_asks_voices() -> None:
    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle([]), voices=voices)

    assert playable.of("film", _PICTURE.key, _CONFIG) is False
    assert voices.calls == []


def test_a_silent_circle_is_not_playable() -> None:
    def _failing(_query: str) -> list[Plan]:
        raise InfraError("прибили")

    playable = ShelfPlayable(circle=_failing, voices=_Voices(heard=object()))

    assert playable.of("film", _PICTURE.key, _CONFIG) is False


def test_a_verdict_of_the_current_rule_is_not_asked_twice() -> None:
    voices = _Voices(heard=object())
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=voices)

    first = playable.of("film", _PICTURE.key, _CONFIG)
    second = playable.of("film", _PICTURE.key, _CONFIG)

    assert first is True and second is True
    assert voices.calls == ["film"], "готовый вердикт того же правила не перепрашивается"


def test_a_rule_change_forgets_the_old_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    voices = _Voices(heard=None)
    playable = ShelfPlayable(circle=_circle([_PLAN]), voices=voices)
    playable.of("film", _PICTURE.key, _CONFIG)

    monkeypatch.setattr("web.shelf_playable.RULE", 99)
    voices.heard = object()
    second = playable.of("film", _PICTURE.key, _CONFIG)

    assert second is True, "новое правило обязано спросить отбор заново"
    assert voices.calls == ["film", "film"]
