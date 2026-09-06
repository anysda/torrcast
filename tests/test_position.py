"""Проверяет вход позиции от вкладки: ``POST /api/web/position``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.adapters.browser.read_web_position import read_web_position
from torrcast.adapters.browser.write_web_box import write_web_box
from torrcast.domain.json_value import JsonValue
from web.position import position
from web.request import Request


def _post(body: dict[str, JsonValue]) -> Request:
    return Request("POST", "/api/web/position", {}, body)


def test_a_matching_key_is_accepted_and_lands_on_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "k1", "pos": 30.0, "dur": 120.0, "phase": "playing"}))

    assert answer.code == 204
    record = read_web_position(tmp_path)
    assert record is not None
    assert record["pos"] == 30.0
    assert record["phase"] == "playing"


def test_a_missing_key_is_refused_as_stale(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"pos": 30.0, "dur": 120.0, "phase": "playing"}))

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "stale_key"}


def test_a_stranger_key_from_a_past_session_is_refused_as_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "old-session", "pos": 30.0, "dur": 120.0, "phase": "playing"}))

    assert answer.code == 409
    assert json.loads(answer.body) == {"error": "stale_key"}


def test_a_word_the_tab_may_not_say_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "k1", "pos": 30.0, "dur": 120.0, "phase": "flying"}))

    assert answer.code == 400
    assert json.loads(answer.body) == {"error": "bad_phase"}


def test_a_position_that_is_not_a_number_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TORRCAST_HLS", str(tmp_path))
    write_web_box(tmp_path, url="u", title="t", at=0.0, key="k1")

    answer = position(_post({"key": "k1", "pos": "далеко", "dur": 120.0, "phase": "playing"}))

    assert answer.code == 400
    assert json.loads(answer.body) == {"error": "bad_number"}
