#!/usr/bin/env python3
"""Reject development-environment traces from the tracked public tree."""

from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Trace:
    name: str
    pattern: re.Pattern[str]
    text_only: bool = False


TRACES = (
    Trace("адрес домашней сети", re.compile(r"192[._]168[._]")),
    Trace("номер контейнера", re.compile(r"\bCT[0-9]{3}\b")),
    Trace("домашний каталог разработчика", re.compile("/home/" + "claude")),
    Trace(
        "рабочий путь суперпользователя",
        re.compile("/" + r"root/(?!(?:[.]cache/pip|Library/Caches/pip)\b)"),
    ),
    Trace("окружение браузерного щупа", re.compile("/opt/" + "pwenv")),
    Trace("внутреннее имя", re.compile(r"\b(?:agent" + r"-ops|caff" + r"eine)\b")),
    Trace("короткий номер машины", re.compile(r"`{1,2}[.][0-9]{1,3}`{1,2}"), True),
    Trace(
        "номер машины рядом со стендом",
        re.compile(r"\b(?:стенд(?:а|е|ом)?|пул(?:а|е)?|приставк(?:а|е|и)?)\s+[.][0-9]{1,3}\b"),
        True,
    ),
    Trace("публичный адрес установки", re.compile(r"(?:ru)?torrcast[.]anysda[.]space")),
)

_PUBLIC = "torrcast" + "." + "anysda" + ".space"
_PUBLIC_RU = "rutorrcast" + "." + "anysda" + ".space"

# Единственный список разрешённых совпадений. Это публичные адреса установки из SPEC §2,
# а не адреса среды разработки; число в каждом файле фиксирует и новые неявные вхождения.
LEGAL_EXCEPTIONS = {
    ("README.md", _PUBLIC): 1,
    ("docs/README-es.md", _PUBLIC): 1,
    ("docs/README-jp.md", _PUBLIC): 1,
    ("docs/README-ru.md", _PUBLIC_RU): 1,
    ("install", _PUBLIC): 2,
    ("torrcast/domain/catalogs/upgrade/en.py", _PUBLIC): 1,
    ("torrcast/domain/catalogs/upgrade/ru.py", _PUBLIC): 1,
}


def _tracked(root: Path) -> list[str]:
    raw = subprocess.check_output(["git", "-C", str(root), "ls-files", "-z"])
    return [name.decode() for name in raw.split(b"\0") if name]


def check(root: Path) -> tuple[list[str], int, int]:
    """Return violations, tracked-file count, and reviewed public endpoint count."""
    violations: list[str] = []
    allowed_seen: dict[tuple[str, str], int] = {}
    tracked = _tracked(root)
    for relative in tracked:
        body = (root / relative).read_bytes()
        binary = b"\0" in body[:8192]
        text = body.decode("utf-8", errors="surrogateescape")
        for number, line in enumerate(text.splitlines(), 1):
            for trace in TRACES:
                if binary and trace.text_only:
                    continue
                for match in trace.pattern.finditer(line):
                    key = (relative, match.group())
                    if key in LEGAL_EXCEPTIONS:
                        allowed_seen[key] = allowed_seen.get(key, 0) + 1
                        continue
                    excerpt = line.strip()[:160]
                    violations.append(f"{relative}:{number}: {trace.name}: {excerpt}")
    tracked_set = set(tracked)
    for key, expected in LEGAL_EXCEPTIONS.items():
        if key[0] not in tracked_set:
            continue
        seen = allowed_seen.get(key, 0)
        if seen != expected:
            violations.append(
                f"{key[0]}: список законных исключений устарел: "
                f"{key[1]} - {seen}, ожидалось {expected}"
            )
    return violations, len(tracked), sum(allowed_seen.values())


def main() -> int:
    root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path(__file__).parents[1]
    violations, files, allowed = check(root)
    if violations:
        print("публичное дерево содержит следы среды разработки:", file=sys.stderr)
        print("\n".join(violations), file=sys.stderr)
        return 1
    checked = f"публичное дерево чисто: проверено файлов: {files}; "
    print(checked + f"законных публичных адресов: {allowed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
