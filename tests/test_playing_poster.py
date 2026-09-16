"""Обложка играющей картины для пульта: полка на месте, сеть - фоном."""

from __future__ import annotations

import time
from pathlib import Path

from hass.poster_lookup import _poster_identity
from hass.poster_shelf import PosterShelf
from tgbot.playing_poster import PlayingPoster
from torrcast.domain.facts.ask import Ask
from torrcast.domain.playback_snapshot import PlaybackSnapshot


def _shown() -> PlaybackSnapshot:
    """Снимок одного показа; обложке хватает имени картины, года и оригинала."""
    return PlaybackSnapshot(key="dune", title="Дюна", year=2021, original="Dune")


def _shelf(home: Path) -> PosterShelf:
    return PosterShelf(lambda: home)


def _awaited(shelf: PosterShelf, identity: str, until: float = 5.0) -> bytes | None:
    """Дождаться байтов на полке по сроку, а не по угаданной задержке сна."""
    deadline = time.monotonic() + until
    while time.monotonic() < deadline:
        body = shelf.read(identity)
        if body:
            return body
        time.sleep(0.02)
    return None


def test_the_shelf_answers_without_asking_the_network(tmp_path: Path) -> None:
    """Лежащая обложка отдаётся на месте: источник за ней не зовут вовсе."""
    asked: list[Ask] = []

    def source(ask: Ask, _timeout: float) -> bytes | None:
        asked.append(ask)
        return b"\xff\xd8network"

    shelf = _shelf(tmp_path)
    poster = PlayingPoster(source, shelf, _shown)
    shelf.write(_identity(), b"\xff\xd8shelf")

    assert poster() == b"\xff\xd8shelf"
    assert asked == []


def test_an_empty_shelf_answers_nothing_and_brings_the_cover_behind_it(
    tmp_path: Path,
) -> None:
    """Пустая полка не держит пульт: ответ пустой сразу, байты ложатся следом."""
    shelf = _shelf(tmp_path)
    poster = PlayingPoster(lambda _ask, _timeout: b"\xff\xd8brought", shelf, _shown)

    assert poster() is None
    assert _awaited(shelf, _identity()) == b"\xff\xd8brought"


def test_a_silent_source_leaves_the_shelf_empty_instead_of_a_stub(tmp_path: Path) -> None:
    """Обложки нет - на полке пусто, и пульт остаётся текстовым, а не с заглушкой."""
    shelf = _shelf(tmp_path)
    poster = PlayingPoster(lambda _ask, _timeout: None, shelf, _shown)

    assert poster() is None
    assert _awaited(shelf, _identity(), until=1.0) is None


def _identity() -> str:
    """Имя картины на полке - то же, которым её зовёт карточка плеера."""
    return _poster_identity(_shown())
