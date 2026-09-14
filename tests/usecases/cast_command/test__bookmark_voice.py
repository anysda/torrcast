"""Живая закладка главнее карточки: дорожка, выбранная на карточке, звучит в раздаче закладки."""

from __future__ import annotations

from typing import Any, cast

import pytest

import torrcast.usecases.playback._launch as launch_module
import torrcast.usecases.select._pick_state as pick_state
import torrcast.usecases.select._voiced as voiced_module
from hass.play_argv import play_argv
from tests.usecases.cast_command.world import entry, plan
from tests.usecases.rank.releases import media, track
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._bookmark import _continue_picked
from torrcast.usecases.start_clock import _Clock

_BOOKMARK = "magnet:?xt=urn:btih:" + "a" * 40
_CARD = "b" * 40


class _Bench:
    def drop_all(self) -> None:
        """Прогретое карточки закладке не нужно."""


class _Engines:
    """TorrServer, который помнит, чью раздачу у него спросили."""

    def __init__(self) -> None:
        self.added: list[str] = []

    def add(self, magnet: str) -> str:
        self.added.append(magnet)
        return "h" * 40

    def wait_files(self, torrent_hash: str, timeout: float) -> None:
        """Файлы раздачи уже на месте."""

    def stream_url(self, torrent_hash: str, file_idx: int) -> str:
        return f"http://ts/{torrent_hash}/{file_idx}"


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> tuple[_Engines, list[Entry]]:
    engines, shown = _Engines(), list[Entry]()
    tracks = (track(0, "rus", "Дубляж"), track(1, "rus", "MVO"), track(2, "eng", "English"))
    monkeypatch.setattr(pick_state, "_select_engines", lambda url: engines)
    monkeypatch.setattr(pick_state, "_select_prober", lambda url, timeout: media(tracks=tracks))
    monkeypatch.setattr(voiced_module, "_held_by_show", lambda torrent_hash: False)
    monkeypatch.setattr(voiced_module, "_release_torrents", lambda config, hashes: None)

    def launch(config: Config, key: str, played: Entry, *rest: object) -> int:
        shown.append(played)
        return 0

    monkeypatch.setattr(launch_module, "_launch", launch)
    return engines, shown


def _play_card(voice: str) -> int | None:
    state = WatchState()
    state.put(plan().picture.key, entry(magnet=_BOOKMARK, audio=0, voice=""))
    argv = play_argv("кино", 1, voice=voice, picture=plan().picture.key, release=_CARD)
    return _continue_picked(
        Config(),
        state,
        cast(Any, plan()),
        _Bench(),  # type: ignore[arg-type]
        args=parse_args([*argv, "--dry"]),
        clock=_Clock(),
    )


def test_a_card_voice_plays_in_the_live_bookmark_release(
    launched: tuple[_Engines, list[Entry]],
) -> None:
    """Карточка раздачи B и English: играет закладка A, и звучит английская дорожка A."""
    engines, shown = launched

    _play_card("eng")

    assert engines.added == [_BOOKMARK]
    assert [(e.magnet, e.audio, e.voice, e.pos) for e in shown] == [(_BOOKMARK, 2, "eng", 3600.0)]


def test_a_voice_the_bookmark_release_lacks_is_refused_not_swapped(
    launched: tuple[_Engines, list[Entry]],
) -> None:
    """Языка в раздаче закладки нет: честный отказ, а не дорожка по умолчанию."""
    with pytest.raises(NotFoundError):
        _play_card("jpn")

    assert launched[1] == []
