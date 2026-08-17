"""Проверяет, что «почему нет картинки» отвечает показ, а не бухгалтерия systemd."""

from __future__ import annotations

import json
import subprocess

import pytest

from torrcast.adapters.systemd import unit_why as module


def _journal(*rows: dict[str, str]) -> object:
    text = "\n".join(json.dumps(row) for row in rows)

    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, text, "")

    return call


def test_the_last_word_is_taken_from_the_show_and_not_from_systemd(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Замер на живой приставке: показ умер, не дав кадра, а наружу уехало «Consumed 5.884s
    CPU time». Последними в журнал юнита пишет systemd, поэтому свои строки отбираются
    по автору записи.
    """
    monkeypatch.setattr(
        module,
        "_systemd",
        _journal(
            {"SYSLOG_IDENTIFIER": "python3.13", "MESSAGE": "рой молчит про раздачу"},
            {"SYSLOG_IDENTIFIER": "python3.13", "MESSAGE": "картинки не было ни разу"},
            {"SYSLOG_IDENTIFIER": "systemd", "MESSAGE": "Consumed 5.884s CPU time"},
        ),
    )
    assert module.unit_why() == "картинки не было ни разу"


def test_a_journal_without_our_lines_says_so_instead_of_inventing_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Своих строк нет - так и говорим. Битая строка журнала не роняет ответ."""
    monkeypatch.setattr(
        module, "_systemd", _journal({"SYSLOG_IDENTIFIER": "systemd", "MESSAGE": "Started."})
    )
    assert module.unit_why() == "в журнале пусто"

    def broken(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, "{не json\n", "")

    monkeypatch.setattr(module, "_systemd", broken)
    assert module.unit_why() == "в журнале пусто"


def test_a_very_long_line_is_cut_before_it_reaches_the_console(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Наружу уходит строка, а не портянка: трейсбек в консоли человеку не ответ."""
    monkeypatch.setattr(
        module,
        "_systemd",
        _journal({"SYSLOG_IDENTIFIER": "python3.13", "MESSAGE": "я" * 500}),
    )
    assert module.unit_why() == "я" * 160
