"""Зеркало отладочной ручки ``cast releases``: своё слово снято, таблица напечатана."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.fakes.blurb_source import FakeBlurbSource
from tests.fakes.blurb_store import FakeBlurbStore
from torrcast.cli.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.release import Release
from torrcast.ports.progress import Progress
from torrcast.runtime.wire import wire
from torrcast.usecases import releases_command
from torrcast.usecases.facts import Facts
from torrcast.usecases.releases_command import _cmd_releases
from torrcast.usecases.select import _Plan

GB = 1024**3


def _silent(wanted: list[tuple[str, int | None]]) -> Facts:
    """Справка, которой нечего сказать: таблица считает по своим числам."""
    return Facts(wanted, 0.0, store=FakeBlurbStore(), source=FakeBlurbSource())


def _plan() -> _Plan:
    release = Release(
        raw_name="Кино / Movie (1999) BDRip 1080p",
        title="Кино",
        year=1999,
        quality="1080p",
        codec="H.264",
        voices=("Дубляж",),
        size=8 * GB,
        seeders=100,
        magnet="magnet-кино",
    )
    return _Plan(
        picture=Picture(title="Кино", year=1999, releases=[release]),
        ranked=[release],
        runtime=120.0 * 60.0,
        warn_mbit=16.0,
    )


def test_the_command_drops_its_own_word_and_prints_the_table(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``cast releases кино`` ищет «кино», а не «releases кино», и печатает таблицу.

    Своё слово команда снимает с запроса сама; останься оно в строке - искали бы не то,
    а номера релизов в таблице считались бы по чужой выдаче. Профиль печатается всегда,
    и последней строкой команда называет, чем сыграть выбранный номер.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    asked: list[list[str]] = []

    def search(config: Config, args: Args, progress: Progress, profile: Profile) -> list[_Plan]:
        asked.append(list(args.query))
        return [_plan()]

    code = _cmd_releases(
        Args(query=["releases", "кино"]),
        search=search,
        settings=Config,
        facts_source=_silent,
        profile_choice=lambda _config: Choice(profile=CAUTIOUS, how="стенд"),
    )
    printed = capsys.readouterr().out
    assert code == EXIT_OK
    assert asked == [["кино"]], "своё слово команда обязана снять с запроса"
    assert "профиль приёмника: " in printed
    assert "Кино" in printed and "1080p" in printed
    assert "играть конкретный: cast <запрос> --release N [--file N]" in printed


def test_an_empty_query_is_an_honest_line_not_a_search(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``cast releases`` без запроса - это вопрос «что искать?», а не поход в каталог."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))

    def never(*_args: Any, **_kwargs: Any) -> list[_Plan]:
        raise AssertionError("искать без запроса нечего")

    with pytest.raises(NotFoundError, match="что искать"):
        _cmd_releases(Args(query=["releases"]), search=never, settings=Config)


def test_the_composition_root_hands_the_command_its_whole_outside_world() -> None:
    """Настройки, справка, паспорт приёмника и память таблицы приходят от корня."""
    wire()
    slots = [name for name in releases_command.__annotations__ if name.startswith("_releases_")]
    assert slots, "у таблицы релизов обязаны быть объявленные слоты внешнего мира"
    assert [name for name in slots if not hasattr(releases_command, name)] == []
