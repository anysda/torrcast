"""Зеркало отказа пульту показу во вкладке: своё слово в ленту, а не молчание."""

from __future__ import annotations

from pathlib import Path

import pytest

from hass.remote_refused import remote_refused
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.config import Config
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install


class _Spy(Silent):
    def __init__(self) -> None:
        self.seen: list[tuple[str, str, dict[str, object]]] = []

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.seen.append((phase, event, fields))


def test_a_tab_box_present_refuses_and_names_the_command_in_the_journal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ящик вкладки лежит - команда пульту не по силам, и почему видно в ленте."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="http://x/out.m3u8", title="Муха", at=0.0, key="k1")
    spy = _Spy()
    install(spy)

    refused = remote_refused(Config(), "seekby")

    assert refused
    assert spy.seen == [("bridge", "remote_refused", {"command": "seekby", "why": "no_remote"})]


def test_no_tab_box_lets_the_command_through(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ящика нет - показ не во вкладке, и пульту тут отказывать не за что."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))

    assert not remote_refused(Config(), "seekby")
