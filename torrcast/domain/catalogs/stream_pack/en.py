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
        "stream_pack.merge_failed": "the splice did not come out",
        "stream_pack.merge_not_seated": "the splice could not be seated on the show tape",
        "stream_pack.astray_both": "the whole splice is off this spot",
        "stream_pack.astray_picture": "the splice's picture is off this spot",
        "stream_pack.astray_sound": "the splice's sound is off this spot",
    }
