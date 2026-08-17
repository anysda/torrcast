"""Печатает карту публичных символов пакета :mod:`torrcast`."""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

MAP_HEADER: Final = """| Символ | Вид | Файл | Строка |
|---|---|---|---:|
"""


@dataclass(frozen=True, order=True)
class Symbol:
    """Один публичный символ верхнего уровня из модуля Python."""

    name: str
    kind: str
    path: str
    line: int


def _public(name: str) -> bool:
    return not name.startswith("_")


def _assigned_names(node: ast.Assign | ast.AnnAssign) -> list[str]:
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    return [target.id for target in targets if isinstance(target, ast.Name) and _public(target.id)]


def symbols(root: Path) -> list[Symbol]:
    """Возвращает публичные классы, функции и константы из ``root/torrcast``."""
    found: list[Symbol] = []
    package = root / "torrcast"
    for path in sorted(package.rglob("*.py")):
        relative = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                if _public(node.name):
                    kind = "класс" if isinstance(node, ast.ClassDef) else "функция"
                    found.append(Symbol(node.name, kind, relative, node.lineno))
            elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                for name in _assigned_names(node):
                    if name.isupper():
                        found.append(Symbol(name, "константа", relative, node.lineno))
    return sorted(found)


def render(root: Path) -> str:
    """Формирует карту для корня репозитория в формате Markdown."""
    rows = [
        f"| `{item.name}` | {item.kind} | `{item.path}` | {item.line} |" for item in symbols(root)
    ]
    return MAP_HEADER + "\n".join(rows) + ("\n" if rows else "")


def main(argv: list[str] | None = None) -> int:
    """Печатает карту в стандартный вывод.

    Файлом она больше не лежит: хранимая копия устаревала на каждой правке, конфликтовала
    в каждом мерже и требовала отдельного правила гейта, чтобы сторожить саму себя. Дом
    символа виден и так - по имени файла, это правило раскладки; карта нужна изредка и
    строится за доли секунды.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    arguments = parser.parse_args(argv)
    sys.stdout.write(render(arguments.root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
