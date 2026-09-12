"""Зеркало отказа пульту показу во вкладке: своё слово в ленту, а не молчание."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hass.remote_refused import remote_refused
from torrcast.adapters.browser.web_box_path import web_box_path
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


def test_a_box_marked_tv_is_not_a_tab_and_the_remote_is_not_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Стык с web-tv (TC-1224). Показ прямо на ТВ тоже заводит ящик - карточке
    вкладки есть что открыть, - и голого ``url`` уже мало, чтобы узнать вкладку: у
    показа на ТВ ящик несёт ``tv: true``. Спутать его с показом во вкладке значило бы
    отказывать боевому пульту Home Assistant на КАЖДОМ показе на ТВ."""
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    path = web_box_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"url": "http://x/out.m3u8", "title": "Муха", "at": 0.0, "tv": True}),
        encoding="utf-8",
    )

    assert not remote_refused(Config(), "seekby")
