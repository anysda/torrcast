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

    assert seen == [
        ("play", "revive", {"pos": 1272.4, "tries": 3, "waited": 41.5, "ok": False, "why": ""})
    ]


def test_the_reason_of_a_failure_stands_in_the_record_and_not_only_in_the_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Поле ``why`` пишется ВСЕГДА, и пустота его значит «причина не названа».

    Пиши его только когда есть что писать - и запись без причины стала бы неотличима
    от записи старой схемы, а разбор ``cast log`` не смог бы сказать, чего он не знает:
    того, что приёмник промолчал, или того, что лента писана до этой правки.
    """
    seen = caught(monkeypatch)

    revive(pos=0.0, tries=1, waited=8.0, ok=False, why="нельзя: приёмник занят чужим показом")

    assert seen[0][2]["why"] == "нельзя: приёмник занят чужим показом"
    assert "why" in seen[0][2], "поле стоит в схеме, а не появляется по случаю"
