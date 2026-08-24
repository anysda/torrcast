"""Проверяет, что «почему нет картинки» отвечает показ, а не бухгалтерия systemd."""

from __future__ import annotations

import json
import subprocess

from torrcast.adapters.systemd._systemd_call import SystemdCall
from torrcast.adapters.systemd.unit_why import unit_why


def _journal(*rows: dict[str, str]) -> SystemdCall:
    text = "\n".join(json.dumps(row) for row in rows)

    def call(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, text, "")

    return call


def test_the_last_word_is_taken_from_the_show_and_not_from_systemd() -> None:
    """🔴 Замер на живой приставке: показ умер, не дав кадра, а наружу уехало «Consumed 5.884s
    CPU time». Последними в журнал юнита пишет systemd, поэтому свои строки отбираются
    по автору записи.
    """
    said = unit_why(
        call=_journal(
            {"SYSLOG_IDENTIFIER": "python3.13", "MESSAGE": "рой молчит про раздачу"},
            {"SYSLOG_IDENTIFIER": "python3.13", "MESSAGE": "картинки не было ни разу"},
            {"SYSLOG_IDENTIFIER": "systemd", "MESSAGE": "Consumed 5.884s CPU time"},
        )
    )
    assert said == "картинки не было ни разу"


def test_a_journal_without_our_lines_says_so_instead_of_inventing_a_reason() -> None:
    """Своих строк нет - так и говорим. Битая строка журнала не роняет ответ."""
    only_systemd = _journal({"SYSLOG_IDENTIFIER": "systemd", "MESSAGE": "Started."})
    assert unit_why(call=only_systemd) == "в журнале пусто"

    def broken(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([tool, *args], 0, "{не json\n", "")

    assert unit_why(call=broken) == "в журнале пусто"


def test_a_very_long_line_is_cut_before_it_reaches_the_console() -> None:
    """Наружу уходит строка, а не портянка: трейсбек в консоли человеку не ответ."""
    long_line = _journal({"SYSLOG_IDENTIFIER": "python3.13", "MESSAGE": "я" * 500})
    assert unit_why(call=long_line) == "я" * 160


def test_a_broken_journal_cannot_kill_the_answer_about_the_unit() -> None:
    """Отказ чтения journald сам становится причиной, а не обрывает команду."""

    def unavailable(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired([tool, *args], 60)

    assert unit_why(call=unavailable).startswith("причина недоступна:")
