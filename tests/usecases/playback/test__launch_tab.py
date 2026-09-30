"""Молчаливое продолжение отдаёт показу ключ вкладки: ``_resume`` не глушит ``--tab``."""

from __future__ import annotations

import pytest

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.usecases.playback import _launch as launch_module
from torrcast.usecases.start_clock import _Clock


def test_resume_hands_the_tab_key_to_the_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    """«Продолжить» у вкладки: ключ едет в запуск, а оттуда в юнит (``start_play_unit``)."""
    tabs: list[str] = []

    def launch(*args: object) -> int:
        tabs.append(str(args[7]))
        return 0

    monkeypatch.setattr(launch_module, "_launch", launch)
    saved = Entry(title="Кино", magnet="magnet:?xt=1", pos=60.0)

    code = launch_module._resume(
        Config(), "movie:кино", saved, _Clock(), here=True, tab="gecko-linux"
    )

    assert code == 0
    assert tabs == ["gecko-linux"]


def test_the_launch_judges_a_hopeless_frame_by_the_tab(monkeypatch: pytest.MonkeyPatch) -> None:
    """Отказ до юнита судит профилем вкладки, которым сыграет юнит, а не детектором без неё."""
    tabs: list[str] = []

    class JudgedError(Exception):
        pass

    def refuse(config: Config, entry: Entry, tab: str = "") -> None:
        tabs.append(tab)
        raise JudgedError

    monkeypatch.setattr(launch_module, "refuse_called_off", lambda: None)
    monkeypatch.setattr(launch_module, "_refuse_hopeless", refuse)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", frame=2160)

    with pytest.raises(JudgedError):
        launch_module._launch(
            Config(), "movie:кино", entry, "Кино", _Clock(), here=True, tab="gecko-linux"
        )

    assert tabs == ["gecko-linux"]
