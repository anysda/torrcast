"""Управляет transient-службой показа через порт запуска процессов."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence

from torrcast.ports.process_runner import ProcessRunner


class SystemdService:
    """Собирает прежние команды systemd, не запуская подпроцессы напрямую."""

    def __init__(
        self,
        runner: ProcessRunner,
        environ: Mapping[str, str] | None = None,
        system: bool | None = None,
    ) -> None:
        self._runner = runner
        self._environ = environ if environ is not None else os.environ
        self._system = os.geteuid() == 0 if system is None else system

    def start(self, key: str, unit: str, tag: str, passed: Sequence[str]) -> None:
        self.stop(unit)
        env = [f"--setenv={name}={self._environ[name]}" for name in passed if name in self._environ]
        command = [
            "systemd-run",
            *self._scope(),
            f"--unit={unit}",
            "--collect",
            "--quiet",
            f"--description={tag}{key}",
            *env,
            sys.executable,
            "-m",
            "torrcast.cli",
            "--play-key",
            key,
        ]
        done = self._runner.run(command)
        if done.returncode != 0:
            reason = done.stderr.strip()[:120] or "systemd-run"
            raise RuntimeError(f"не запустился юнит {unit}: {reason}")

    def stop(self, unit: str) -> None:
        self._runner.run(["systemctl", *self._scope(), "stop", unit])

    def active(self, unit: str) -> bool:
        done = self._runner.run(["systemctl", *self._scope(), "is-active", unit])
        return done.stdout.strip() == "active"

    def key(self, unit: str, tag: str) -> str:
        done = self._runner.run(
            ["systemctl", *self._scope(), "show", unit, "-p", "Description", "--value"]
        )
        description = done.stdout.strip()
        return description[len(tag) :].strip() if description.startswith(tag) else ""

    def why(self, unit: str) -> str:
        command = [
            "journalctl",
            "-u",
            unit,
            "-n",
            "30",
            "--no-pager",
            "-o",
            "json",
            "--output-fields=MESSAGE,SYSLOG_IDENTIFIER",
        ]
        done = self._runner.run(command)
        ours: list[str] = []
        for line in done.stdout.splitlines():
            try:
                record = json.loads(line)
            except (ValueError, TypeError):
                continue
            if record.get("SYSLOG_IDENTIFIER") != "systemd":
                message = str(record.get("MESSAGE") or "").strip()
                if message:
                    ours.append(message)
        return ours[-1][:160] if ours else "в журнале пусто"

    def _scope(self) -> list[str]:
        return [] if self._system else ["--user"]
