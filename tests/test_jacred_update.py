"""The catalogue updater avoids a full archive download when the ETag is unchanged."""

import importlib.util
import urllib.error
from email.message import Message
from pathlib import Path
from typing import NoReturn
from urllib.request import Request

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jacred_update", Path(__file__).parents[1] / "scripts/jacred-update.py"
)
assert SPEC and SPEC.loader
updater = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(updater)


def test_an_unchanged_archive_keeps_the_live_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "index.sqlite"
    target.write_bytes(b"published")
    updater._etag_file(target).write_text('"old"\n')
    asked: list[str | None] = []

    def unchanged(request: Request, timeout: float) -> NoReturn:
        asked.append(request.get_header("If-none-match"))
        raise urllib.error.HTTPError("https://example.invalid", 304, "unchanged", Message(), None)

    monkeypatch.setattr(updater.urllib.request, "urlopen", unchanged)

    assert updater.refresh(target) is None
    assert asked == ['"old"']
    assert target.read_bytes() == b"published"
