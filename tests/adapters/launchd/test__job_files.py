"""Проверяет, что файлы задания лежат во временном каталоге и зовутся по метке."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from torrcast.adapters.launchd._job_files import _log_path, _plist_path


@pytest.fixture
def scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Временный каталог на время теста - его личный, а не хозяйский."""
    monkeypatch.setattr(tempfile, "gettempdir", lambda: str(tmp_path))
    return tmp_path


def test_the_files_of_a_job_are_named_after_its_label(scratch: Path) -> None:
    """Метка задания - единственное имя, которое у него есть: файлы зовутся ей же.

    У системного и пользовательского задания временные каталоги свои - как и области,
    поэтому в путях нет ни uid, ни области: их разводит сам каталог.
    """
    assert _plist_path("torrcast-play") == scratch / "torrcast-play.plist"
    assert _log_path("torrcast-play") == scratch / "torrcast-play.log"
    assert _plist_path("torrcast.проба") == scratch / "torrcast.проба.plist"
