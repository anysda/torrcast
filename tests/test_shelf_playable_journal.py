"""Проверяет строку журнала о плитке, которую полка снимает приговором «не играет»."""

from __future__ import annotations

from typing import Any

import pytest

from torrcast.domain.config import Config
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.shelf_playable import ShelfPlayable

_RELEASE = Release(raw_name="Film 2010 BDRip 1080p LostFilm", title="Film", magnet="magnet:f")
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_RELEASE])
_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE], runtime=0, warn_mbit=0)
_CONFIG = Config(torrserver_url="http://ts", receiver_profile="q70d")


def _alive(_config: Config) -> bool:
    return True


def _voices(heard: Any) -> Any:
    return lambda _plan, _query, _config: (heard, False, True)


def test_a_dropped_tile_is_named_in_the_journal_once(capsys: pytest.CaptureFixture[str]) -> None:
    """«Не играет» снимает плитку: журнал называет запрос и ключ, повтор из памяти молчит."""
    playable = ShelfPlayable(circle=lambda _q: [_PLAN], voices=_voices(None), alive=_alive)

    assert playable.of("Film", _PICTURE.key, _CONFIG) is False
    assert playable.of("Film", _PICTURE.key, _CONFIG) is False

    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 1
    assert "Film" in lines[0] and _PICTURE.key in lines[0]


def test_a_playable_or_unknown_tile_leaves_no_drop_line(capsys: pytest.CaptureFixture[str]) -> None:
    """«Играет» и «не знаю» плитку не снимают, и строки о снятии нет."""
    playing = ShelfPlayable(circle=lambda _q: [_PLAN], voices=_voices(object()), alive=_alive)
    unknown = ShelfPlayable(circle=lambda _q: [], voices=_voices(None), alive=_alive)

    assert playing.of("Film", _PICTURE.key, _CONFIG) is True
    assert unknown.of("Film", _PICTURE.key, _CONFIG) is None

    assert capsys.readouterr().out == ""
