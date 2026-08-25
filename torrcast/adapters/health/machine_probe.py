"""Как узнать про саму машину: терминал, локаль, память, диск, серт, полки и след.

Половина системной среды :mod:`torrcast.adapters.health.system_health_environment`.
"""

import contextlib
import locale
import os
import sys
import time
from pathlib import Path
from typing import Any

from torrcast.adapters.console.console import stdin_is_tty as _tty
from torrcast.adapters.console.console.iutf8 import iutf8
from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.trace_journal.health import health as trace_health
from torrcast.adapters.filesystem.trace_journal.log_dir import log_dir
from torrcast.adapters.filesystem.trace_journal.prune import RETAIN_DAYS
from torrcast.adapters.stream_probe.shelf_weight import shelf_weight
from torrcast.domain.warm_open import KEYS_KEPT, PROBE_KEPT
from torrcast.domain.warm_settings import WARM_DIR

#: Имена переменных окружения, которыми задаётся локаль: их и показываем человеку.
_LOCALE_NAMES = ("LANG", "LC_ALL", "LC_CTYPE")


class MachineProbe:
    """Факты о машине, на которой запущен ``cast``: диск, память, часы и терминал."""

    @staticmethod
    def has_terminal() -> bool:
        """Есть ли живой pty на входе: без него вопросы возьмут дефолты."""
        return _tty.stdin_is_tty()

    @staticmethod
    def terminal_utf8() -> bool | None:
        """Включён ли ``IUTF8``; ``None`` - режим ввода не читается вовсе."""
        import termios

        try:
            mode = termios.tcgetattr(sys.stdin.fileno())
        except (termios.error, ValueError, OSError):
            return None
        return bool(int(mode[0]) & iutf8())

    @staticmethod
    def encoding() -> str:
        """Предпочтительная кодировка процесса, в нижнем регистре."""
        return (locale.getpreferredencoding(False) or "").lower()

    @staticmethod
    def locale_env() -> str:
        """Переменные окружения, которыми локаль задана, одной строкой."""
        return " ".join(
            f"{name}={os.environ[name]}" for name in _LOCALE_NAMES if name in os.environ
        )

    @staticmethod
    def machine_memory() -> int:
        """Память, которая есть у ЭТОЙ машины, байты - с оглядкой на cgroup.

        В контейнере ``/proc/meminfo`` показывает не то, что дадут: потолок стоит на cgroup,
        и упирается показ именно в него. Берём меньшее из двух.
        """
        total = 0
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) * 1024
        except (OSError, ValueError, IndexError):
            return 0
        for path in ("/sys/fs/cgroup/memory.max", "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
            try:
                limit = int(Path(path).read_text().strip())
            except (OSError, ValueError):
                continue
            if 0 < limit < total:
                total = limit
        return total

    @staticmethod
    def disk_free(path: str) -> int:
        """Свободное место на разделе ``path``, байты; каталога нет - спрашиваем предка."""
        place = Path(path)
        while not place.exists() and place != place.parent:
            place = place.parent
        try:
            stat = os.statvfs(place)
        except OSError:
            return 0
        return stat.f_bavail * stat.f_frsize

    @staticmethod
    def warm_used() -> int:
        """Сколько байт уже занято прогретым в его каталоге (:data:`WARM_DIR`).

        🔴 TC-725. Спрашивается ради резерва под кэш раздачи: свободное место раздела
        занятого прогревом уже не содержит, и без этого числа бюджет прогрева считался
        бы поверх собственных файлов (:func:`torrcast.domain.warm_claim.warm_claim`).
        Считаются только куски показа - каталог общий с чужими файлами не бывает, но
        паспорта и огрызки прогона к бюджету не относятся.
        """
        total = 0
        with contextlib.suppress(OSError):
            for mask in ("v*.ts", "v*.m4s"):
                for piece in Path(WARM_DIR).rglob(mask):
                    with contextlib.suppress(OSError):
                        total += piece.stat().st_size
        return total

    @staticmethod
    def cert_days(path: str) -> int | None:
        """Сколько дней осталось серту; ``None`` - файла нет или он не разбирается."""
        import ssl
        from datetime import UTC, datetime

        decode: Any = getattr(ssl, "_ssl", None)  # штатного API «прочитать серт с диска» нет
        if decode is None:
            return None
        try:
            until = str(decode._test_decode_cert(str(Path(path)))["notAfter"])
        except (OSError, ValueError, KeyError, TypeError):
            return None
        stamp = datetime.strptime(until, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=UTC)
        return (stamp - datetime.now(UTC)).days

    @staticmethod
    def shelves() -> tuple[str, tuple[int, int], tuple[int, int]]:
        """Каталог полок и вес каждой: карты опорных кадров и паспорта."""
        shelf = state_path().parent
        return str(shelf), shelf_weight(shelf / "keys"), shelf_weight(shelf / "probe")

    @staticmethod
    def shelf_limits() -> tuple[int, int]:
        """Потолки тех же полок: сколько записей на них вообще доживает."""
        return KEYS_KEPT, PROBE_KEPT

    @staticmethod
    def trace_health() -> tuple[bool, float, int]:
        """Здоровье недельной ленты: есть ли, когда писали последний раз, сколько весит."""
        found, newest, total = trace_health()
        return bool(found), float(newest), int(total)

    @staticmethod
    def trace_dir() -> str:
        """Каталог, в котором лента живёт."""
        return str(log_dir())

    @staticmethod
    def retain_days() -> int:
        """Сколько суток лента хранится: старше этого - уже протухла."""
        return int(RETAIN_DAYS)

    @staticmethod
    def now() -> float:
        """Настенные часы: возраст записи считается от них."""
        return time.time()
