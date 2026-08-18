"""Зеркало продолжения по состоянию: когда оно отвечает само, а когда уступает поиску."""

from __future__ import annotations

from collections.abc import Callable

from tests.usecases.select.world import entry
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.start_clock import _Clock

_SERIES: dict[str, object] = {
    "kind": "tv",
    "season": 1,
    "episode": 2,
    "episodes": [[1, 1, 0], [1, 2, 1], [1, 3, 2]],
}


class _Shown:
    """Показ, который никуда не уезжает, а запоминает, с чем его позвали."""

    def __init__(self) -> None:
        self.launched: list[tuple[str, str]] = []
        self.resumed: list[str] = []

    def launch(
        self, config: Config, key: str, saved: Entry, about: str, clock: _Clock, dry: bool = False
    ) -> int:
        self.launched.append((saved.label, about))
        return EXIT_OK

    def resume(
        self, config: Config, key: str, saved: Entry, clock: _Clock, dry: bool = False
    ) -> int:
        self.resumed.append(saved.title)
        return EXIT_OK

    @property
    def calls(self) -> dict[str, Callable[..., int]]:
        """Оба соседа продолжения разом - ровно теми именами, какими их зовут."""
        return {"launch": self.launch, "resume": self.resume}


def test_a_film_with_nothing_to_continue_gives_way_to_the_usual_path() -> None:
    """Продолжать нечего - озвучку выберет обычный путь, по дорожкам потока."""
    shown = _Shown()

    code = _continue(
        Config(),
        "movie:кино:1999",
        entry(pos=0.0),
        Args(query=["кино"]),
        _Clock(),
        **shown.calls,
    )

    assert code is None
    assert (shown.launched, shown.resumed) == ([], [])


def test_a_film_in_the_middle_is_resumed_without_a_single_question() -> None:
    """Релиз, дорожка, файл и позиция уже записаны - спрашивать нечего."""
    shown = _Shown()

    code = _continue(
        Config(), "movie:кино:1999", entry(), Args(query=["кино"]), _Clock(), **shown.calls
    )

    assert code == EXIT_OK
    assert shown.resumed == ["Кино"]


def test_an_asked_episode_jumps_by_the_cache_of_the_torrent() -> None:
    """`cast кино s1e3` - прыжок по кэшу раздачи, без Prowlarr и без вопросов."""
    saved, shown = entry(**_SERIES), _Shown()

    code = _continue(
        Config(), "tv:кино", saved, Args(query=["кино", "s1e3"]), _Clock(), **shown.calls
    )

    assert code == EXIT_OK
    assert [label for label, _about in shown.launched] == ["s1e3"]


def test_an_episode_the_torrent_does_not_have_goes_looking_for_a_release() -> None:
    """Серии в этой раздаче нет - честно идём искать релиз сезона, а не врём отказом."""
    saved, shown = entry(**_SERIES), _Shown()

    code = _continue(
        Config(), "tv:кино", saved, Args(query=["кино", "s9e1"]), _Clock(), **shown.calls
    )

    assert code is None
    assert shown.launched == []
