"""Достаёт из journald последнюю внятную строку самого показа; зовут отчёты о беде."""

from __future__ import annotations

import contextlib
import json

from torrcast.adapters.systemd._systemd_call import _systemd
from torrcast.domain.unit_naming import _UNIT_NAME


def unit_why(unit: str = _UNIT_NAME) -> str:
    """Последняя внятная строка САМОГО ПОКАЗА из journald — наружу без трейсбеков.

    🔴 Спрашивают отсюда одно: почему на экране нет картинки, - и отвечать на это
    бухгалтерией systemd нельзя. Замер 16-08-2026 на живой приставке: показ умер, не дав
    ни кадра, и человек у консоли получил «показ не запустился: torrcast-play.service:
    Consumed 5.884s CPU time, 175.4M memory peak». Про беду в этой строке нет ничего:
    последними в журнал юнита пишет не показ, а systemd - о запуске, остановке и
    потраченном процессоре. Поэтому свои строки отбираются по автору записи, а глубина
    поиска берётся с запасом на его послесловие.
    """
    done = _systemd(
        "journalctl", "-u", unit, "-n", "30", "--no-pager",
        "-o", "json", "--output-fields=MESSAGE,SYSLOG_IDENTIFIER",
    )  # fmt: skip
    ours: list[str] = []
    for line in done.stdout.splitlines():
        with contextlib.suppress(ValueError, TypeError):
            record = json.loads(line)
            if record.get("SYSLOG_IDENTIFIER") != "systemd":
                text = str(record.get("MESSAGE") or "").strip()
                if text:
                    ours.append(text)
    return ours[-1][:160] if ours else "в журнале пусто"
