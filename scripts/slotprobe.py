#!/usr/bin/env python3
"""Отрицательная проба сторожа проводок: краснеет ли правило на каждом своём слоте.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python scripts/slotprobe.py
    python scripts/slotprobe.py --only wire_show

Сторож берётся не отсюда, а вырезается из живого ``scripts/test-gate``: щуп обязан
проверять ТО правило, которое стоит в гейте, иначе он доказывает свою копию.

На каждый слот две пробы, и обе обязаны краснеть:

* **сторож** - из зеркала вырезается строка сверки этого слота, и сторож гейта должен
  назвать слот слепым. Промолчал - правило куплено входом, а не выполнено;
* **зеркало** - в проводке довод этого слота подменяется пустышкой ``object()``, и тест
  зеркала должен упасть. Прошёл зелёным - сверка не сверяет ничего.

⚠️ Байткод пробы пишется мимо диска (``PYTHONDONTWRITEBYTECODE``): подмена меняет файл,
но не всегда его длину, а протухший ``__pycache__`` врёт в обе стороны сразу.
"""

from __future__ import annotations

import argparse
import ast
import contextlib
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

GATE = Path("scripts/test-gate")
#: Начало и конец врезки сторожа в гейте: тем же куском он туда и попадает.
OPEN, CLOSE = ".venv/bin/python - <<'PY'\n", "\nPY\n"


def guard_source() -> str:
    """Сторож ровно тем текстом, каким его исполняет гейт."""
    gate = GATE.read_text(encoding="utf-8")
    start = gate.index(OPEN) + len(OPEN)
    return gate[start : gate.index(CLOSE, start)]


def guard_names(source: str) -> dict[str, Any]:
    """Разбор сторожа как библиотеки: он же считает слоты, он же их и называет."""
    names: dict[str, Any] = {}
    # Сторож на здоровом дереве молча доходит до конца, на порченом - выходит с
    # SystemExit: щупу нужны его имена в обоих случаях.
    with contextlib.suppress(SystemExit):
        exec(compile(source, "test-gate:сторож", "exec"), names)
    return names


def guard_says(source: str) -> str:
    """Что сторож сказал на порченом дереве; пусто - промолчал и пропустил."""
    done = subprocess.run(
        [".venv/bin/python", "-c", source], capture_output=True, text=True, check=False
    )
    return done.stdout + done.stderr if done.returncode else ""


def mirror_is_green(mirror: str) -> bool:
    done = subprocess.run(
        [
            ".venv/bin/python",
            "-m",
            "pytest",
            mirror,
            "-q",
            "-n",
            "0",
            "-x",
            "-p",
            "no:cacheprovider",
        ],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
    )
    return done.returncode == 0


def compare_lines(mirror: str, names: dict[str, Any]) -> dict[tuple[str, str], int]:
    """На какой строке зеркала стоит сверка каждого слота."""
    mod = ast.parse(Path(mirror).read_text(encoding="utf-8"))
    known = names["imports"](mod)
    out: dict[tuple[str, str], int] = {}
    for node in ast.walk(mod):
        if not isinstance(node, ast.Compare) or len(node.ops) != 1:
            continue
        left = node.left
        if (
            isinstance(left, ast.Call)
            and isinstance(left.func, ast.Name)
            and left.func.id == "type"
        ):
            left = left.args[0]
        if not isinstance(left, ast.Attribute) or not isinstance(left.value, ast.Name):
            continue
        where = known.get(left.value.id)
        if where:
            out[(where[0], left.attr)] = node.lineno
    return out


def spoiled(source: str, value: str) -> str | None:
    """Тот же довод пустышкой: ровно одно вхождение и по границе слова."""
    if value.startswith("класс "):
        value = value[len("класс ") :] + "()"
    hit = re.compile(rf"(?<![\w.]){re.escape(value)}(?![\w(])")
    text, count = hit.subn("object()", source, count=1)
    return text if count else None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", default="", help="проверить одну проводку: wire_show")
    only = parser.parse_args().only
    source = guard_source()
    names = guard_names(source)
    bad: list[str] = []
    checked = 0
    for wiring, mirror in names["WIRINGS"].items():
        if only and only not in wiring:
            continue
        asked = names["wanted"](wiring)
        lines = compare_lines(mirror, names)
        keep_mirror = Path(mirror).read_text(encoding="utf-8")
        keep_wiring = Path(wiring).read_text(encoding="utf-8")
        for (state, slot), value in sorted(asked.items()):
            checked += 1
            line = lines.get((state, slot))
            if line is None:
                bad.append(f"{state}.{slot}: сверки в зеркале не нашлось вовсе")
                continue
            rows = keep_mirror.splitlines(keepends=True)
            Path(mirror).write_text("".join(rows[: line - 1] + rows[line:]), encoding="utf-8")
            said = guard_says(source)
            Path(mirror).write_text(keep_mirror, encoding="utf-8")
            if f"{state}.{slot}" not in said:
                bad.append(f"{state}.{slot}: сторож промолчал на вырезанной сверке")
                continue
            broken = spoiled(keep_wiring, value)
            if broken is None:
                bad.append(f"{state}.{slot}: довод {value} в проводке не нашёлся")
                continue
            Path(wiring).write_text(broken, encoding="utf-8")
            green = mirror_is_green(mirror)
            Path(wiring).write_text(keep_wiring, encoding="utf-8")
            if green:
                bad.append(f"{state}.{slot}: зеркало зелёное на пустышке вместо {value}")
                continue
            print(f"  {state.split('.')[-1]}.{slot}: обе пробы красные", flush=True)
    print(f"\nслотов проверено: {checked}, брака: {len(bad)}")
    for row in bad:
        print("  ", row)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
