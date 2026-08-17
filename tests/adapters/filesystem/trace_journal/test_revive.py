"""Схема ``play/revive``: попытка поднять погасший показ и её честный исход."""

from __future__ import annotations

import pytest

from tests.adapters.filesystem.trace_journal.tape import caught
from torrcast.adapters.filesystem.trace_journal.revive import revive


def test_a_failed_resurrection_is_written_as_carefully_as_a_successful_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ложь в ``ok`` не хуже правды: по ней видно, сколько раз подъём не удался.

    Записывай след только удачи - и погасший навсегда показ выглядел бы в ленте как
    показ, который никто и не пытался поднять.
    """
    seen = caught(monkeypatch)

    revive(pos=1272.44, tries=3, waited=41.46, ok=False)

    assert seen == [("play", "revive", {"pos": 1272.4, "tries": 3, "waited": 41.5, "ok": False})]
