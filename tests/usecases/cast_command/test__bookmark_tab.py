"""Закладка с нуля играет порогами той вкладки, что попросила: ключ ``--tab`` не теряется."""

from __future__ import annotations

import pytest

from tests.usecases.cast_command.world import entry
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.usecases.cast_command import _bookmark
from torrcast.usecases.start_clock import _Clock


@pytest.mark.parametrize(
    "asked",
    [
        Args(query=["кино"], here=True, from_start=True, tab="gecko-linux"),
        Args(query=["кино", "s1e1"], here=True, from_start=True, tab="gecko-linux"),
    ],
    ids=["from-zero", "named-episode"],
)
def test_the_tab_that_asked_is_handed_to_the_show_from_zero(
    monkeypatch: pytest.MonkeyPatch, asked: Args
) -> None:
    """«С начала» у вкладки: показ получает её ключ, иначе юнит судил бы её порогами ТВ."""
    tabs: list[str] = []

    def launch(*args: object) -> int:
        tabs.append(str(args[7]))
        return 0

    monkeypatch.setattr(_bookmark, "_launch", launch)
    saved = entry(kind="tv", season=1, episode=2, episodes=[[1, 1, 0], [1, 2, 1]])

    assert _bookmark._from_start(Config(), "tv:кино", saved, args=asked, clock=_Clock()) == 0
    assert tabs == ["gecko-linux"]
