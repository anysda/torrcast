"""Отдельный сеанс на каждый фильм или серию: суффикс не даёт им склеиться в ленте.

Зовёт его показ на границе картины, и больше никто."""

from __future__ import annotations

import os
import time

from torrcast.adapters.filesystem.trace_journal.session_id import SID_ENV

#: Счётчик и корень сеансов держатся здесь, а не в окружении: окружение несёт готовый
#: идентификатор, а из него не видно, какой он по счёту у этого вызова ``cast``.
_session_seq = 0
_session_root = ""
_last_session = ""


def start_session() -> str:
    """Начать отдельный сеанс показа и вернуть его идентификатор.

    Вызывается один раз на границе фильма или серии, не из горячего пути. Родительский
    идентификатор сохраняет связь с вызовом ``cast``, суффикс не даёт сериям склеиться.
    """
    global _last_session, _session_root, _session_seq
    current = os.environ.get(SID_ENV, "")
    if current != _last_session:
        _session_root = current or f"{int(time.time())}-{os.getpid()}"
        _session_seq = 0
    _session_seq += 1
    sid = f"{_session_root}.{_session_seq}"
    os.environ[SID_ENV] = sid
    _last_session = sid
    return sid
