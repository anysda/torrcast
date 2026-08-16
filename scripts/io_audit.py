"""Считает прямой ввод-вывод в модулях, которые ещё не разложены по слоям.

Мера готовности разреза: сеть, диск, подпроцессы и часы обязаны уехать в
`torrcast/adapters/`, а старый модуль остаться фасадом. Структурный гейт этого не
ловит — правило `ввод-вывод` освобождает слой «не разложено», то есть ровно те
плоские модули, которые и режутся. Отсюда отдельный счётчик.

    io-audit torrcast/search.py torrcast/stream_core.py
    io-audit --strict torrcast/search.py

Жёсткие — сеть, подпроцессы, файлы и сон: их в неразложенном модуле быть не должно.
Мягкие — работа с путями как со значениями: их наличие само по себе не нарушение.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path
from typing import Final

HARD: Final = frozenset(
    {
        "requests",
        "socket",
        "subprocess",
        "shutil",
        "tempfile",
        "pychromecast",
        "zeroconf",
        "urllib.request",
        "urllib.error",
        "http.client",
        "http.server",
    }
)
HARD_CALLS: Final = frozenset({"open", "time.sleep", "os.system", "os.remove", "os.makedirs"})
# Диск через `pathlib` выглядит как обычный вызов метода: сам импорт мягкий, а вот
# чтение и запись — тот же ввод-вывод, что и `open`.
HARD_METHODS: Final = frozenset(
    {
        "read_text",
        "write_text",
        "read_bytes",
        "write_bytes",
        "mkdir",
        "unlink",
        "rmdir",
        "touch",
        "iterdir",
        "rename",
    }
)
SOFT: Final = frozenset({"pathlib", "os.path", "urllib.parse"})


def _module_of(node: ast.Import | ast.ImportFrom, alias: ast.alias) -> str:
    """Возвращает полное имя импортируемого модуля."""
    if isinstance(node, ast.ImportFrom):
        return node.module or ""
    return alias.name


def _matches(name: str, family: frozenset[str]) -> bool:
    """Проверяет принадлежность имени семейству, считая точку границей."""
    return any(name == item or name.startswith(f"{item}.") for item in family)


def hits(path: Path) -> tuple[list[str], list[str]]:
    """Возвращает жёсткие и мягкие нарушения одного модуля."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    hard: list[str] = []
    soft: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = _module_of(node, alias)
                if _matches(name, HARD):
                    hard.append(f"{node.lineno}: {name}")
                elif _matches(name, SOFT):
                    soft.append(f"{node.lineno}: {name}")
        elif isinstance(node, ast.Call):
            call = ast.unparse(node.func)
            if call in HARD_CALLS:
                hard.append(f"{node.lineno}: {call}()")
            elif isinstance(node.func, ast.Attribute) and node.func.attr in HARD_METHODS:
                hard.append(f"{node.lineno}: .{node.func.attr}()")
    return hard, soft


def main(argv: list[str] | None = None) -> int:
    """Печатает счётчик по каждому запрошенному модулю."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true")
    arguments = parser.parse_args(argv)
    paths = arguments.paths or sorted((arguments.root / "torrcast").glob("*.py"))
    total = 0
    for path in paths:
        full = path if path.is_absolute() else arguments.root / path
        if not full.exists():
            print(f"{path} — нет файла")
            continue
        hard, soft = hits(full)
        total += len(hard)
        print(f"{path!s:34} жёстких {len(hard):3}  мягких {len(soft):3}  {'; '.join(hard[:3])}")
    print(f"{'ИТОГО жёстких':34} {total:3}")
    return int(arguments.strict and bool(total))


if __name__ == "__main__":
    sys.exit(main())
