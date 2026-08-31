"""Английский каталог кластера ``stream_pack``: он же умолчание, он же запасной."""

from __future__ import annotations


def en() -> dict[str, str]:
    return {
        "stream_pack.paused_from_remote": "paused from the remote",
        "stream_pack.flag_write_failed": "playing flag did not land ({flag}): {reason}",
        "stream_pack.stopped_ourselves": "stopped ourselves: {reason}",
        "stream_pack.killed_by_signal": "killed by signal {signal}",
        "stream_pack.no_output": "no output",
        "stream_pack.silent_with_code": "silent, code {code}",
    }
