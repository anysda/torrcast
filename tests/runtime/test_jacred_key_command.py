"""Сценарий ключа JacRed хранит секрет, но подтверждает только факт."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast.runtime.jacred_key_command import jacred_key_command
from torrcast.runtime.wire import wire


def test_key_is_saved_without_printing_it(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    wire()

    assert jacred_key_command("test-key") == 0

    stored = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert stored["jacred_key"] == "test-key"
    assert "test-key" not in capsys.readouterr().out
