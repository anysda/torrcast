"""Считает, сколько кода ещё живёт в неразложенном модуле, а не переехало в слой.

Мера готовности разреза, парная к `io-audit`: после переезда старый модуль обязан
остаться фасадом — импорты перенесённого плюс статический `__all__`, и ничего
своего. Структурный гейт этого не видит: плоский модуль для него «не разложено»,
а зелёный прогон одинаково доволен и переездом, и копией рядом.

    facade-audit torrcast/commands.py torrcast/stream.py
    facade-audit --strict torrcast/commands.py

Считаются определения верхнего уровня и строки их тел. У фасада и то и другое ноль.
"""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

DEFINITION = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _body_lines(node: ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef) -> int:
    """Возвращает число строк, занятых определением."""
    end = node.end_lineno if node.end_lineno is not None else node.lineno
    return end - node.lineno + 1


def hits(path: Path) -> tuple[list[str], int]:
    """Возвращает определения верхнего уровня модуля и суммарный их размер."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: list[str] = []
    lines = 0
    for node in tree.body:
        if isinstance(node, DEFINITION):
            names.append(f"{node.lineno}: {node.name}")
            lines += _body_lines(node)
    return names, lines


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
        names, lines = hits(full)
        total += len(names)
        print(f"{path!s:32} единиц {len(names):3}  строк в них {lines:5}  {'; '.join(names[:3])}")
    print(f"{'ИТОГО единиц на месте':32} {total:3}")
    return int(arguments.strict and bool(total))


if __name__ == "__main__":
    sys.exit(main())
