#!/usr/bin/env python3
"""Сторож подписи: у каждого числа приёмника назван прибор, которым оно снято.

Инструмент разработчика: в устанавливаемый пакет не входит.

    python3 scripts/probesign.py
    python3 scripts/probesign.py torrcast/domain/profile.py

Предмет - профили приёмников (:mod:`torrcast.domain.profile`): это потолки, которыми
живёт показ, и снимаются они только живьём. Спрашивается два разных долга:

1. каждое переопределённое поле профиля подписано на СВОЕЙ строке. Подпись соседа не
   годится: блок комментария в этом файле стоит то над своим полем, то над чужим, и
   «подпись сверху» приписала бы прибор не тому числу;
2. каждый блок комментария внутри профиля, который ссылается на замер, подписан сам.
   Этим ловится то, чего первый долг не видит вовсе: заявление о НЕ переопределённом
   поле («нули сторожа тут не тронуты, и это замер») числа не имеет, а прибора требует
   ровно так же.

🔴 Порог тут ноль, и опускать его нечем: подпись :data:`~probestamp.UNNAMED` разрешена и
закрывает долг формально, но остаётся греповым признаком того, что прибор не восстановлен.
Молчание же от «снято щупом» не отличается ничем - ровно так и появился TC-870.
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import sys
import tokenize
from pathlib import Path
from typing import Final

sys.path.insert(0, str(Path(__file__).resolve().parent))

from probestamp import APART, SIGN, TOOLS, TRACTS, UNNAMED

#: Корень репозитория: у щупа он один - родитель ``scripts/``.
ROOT: Final = Path(__file__).resolve().parent.parent
#: Что спрашивается по умолчанию.
PROFILES: Final = "torrcast/domain/profile.py"
#: Поля профиля, которые ничего не меряют: имя ключа и подпись для человека.
NOT_MEASURED: Final = frozenset({"key", "title"})
#: Слова, которыми комментарий ссылается на замер. Ссылается - значит обязан назвать чем.
MEASURED: Final = re.compile(r"замер|измер|снят|живь[её]м|жив(ой|ых|ого)|прогон")


def unsigned(source: str) -> list[str]:
    """Места профилей приёмника, где прибор замера не назван; пусто - долгов нет."""
    tree = ast.parse(source)
    lines = source.splitlines()
    comments = _comments(source)
    faults: list[str] = []
    for name, call in _profiles(tree):
        for keyword in call.keywords:
            if keyword.arg is None or keyword.arg in NOT_MEASURED:
                continue
            said = comments.get(keyword.value.lineno, "")
            faults += _faults(f"{name}.{keyword.arg}", said)
        for first, text in _blocks(call, lines, comments):
            if MEASURED.search(text):
                faults += _faults(f"{name}, блок про замер со строки {first}", text)
    return faults


def _profiles(tree: ast.Module) -> list[tuple[str, ast.Call]]:
    """Сборки профилей верхнего уровня: имя константы и сам вызов ``Profile(...)``."""
    found: list[tuple[str, ast.Call]] = []
    for node in tree.body:
        target: ast.expr
        value: ast.expr | None
        if isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        else:
            continue
        if not isinstance(target, ast.Name) or not isinstance(value, ast.Call):
            continue
        if isinstance(value.func, ast.Name) and value.func.id == "Profile":
            found.append((target.id, value))
    return found


def _comments(source: str) -> dict[int, str]:
    """Комментарии исходника по номеру строки. Токенайзером, а не поиском решётки:
    решётка внутри строкового литерала комментарием не является."""
    found: dict[int, str] = {}
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type == tokenize.COMMENT:
            found[token.start[0]] = token.string
    return found


def _blocks(call: ast.Call, lines: list[str], comments: dict[int, str]) -> list[tuple[int, str]]:
    """Сплошные блоки цельнострочных комментариев внутри вызова: строка начала и текст."""
    inside = [
        number
        for number in sorted(comments)
        if call.lineno <= number <= (call.end_lineno or call.lineno)
        and lines[number - 1].lstrip().startswith("#")
    ]
    blocks: list[tuple[int, str]] = []
    for number in inside:
        if blocks and number - 1 == _last(blocks):
            blocks[-1] = (blocks[-1][0], f"{blocks[-1][1]}\n{comments[number]}")
        else:
            blocks.append((number, comments[number]))
    return blocks


def _last(blocks: list[tuple[int, str]]) -> int:
    """Номер последней строки последнего блока."""
    first, text = blocks[-1]
    return first + text.count("\n")


def _faults(where: str, text: str) -> list[str]:
    """Что не так с подписью в этом тексте: пусто - подпись на месте и разобрана."""
    if SIGN not in text:
        return [f"{where}: прибор замера не назван (нет «{SIGN}»)"]
    tail = text[text.index(SIGN) + len(SIGN) :].splitlines()[0]
    parts = [part.strip() for part in tail.split(APART.strip()) if part.strip()]
    if len(parts) < 3:
        return [f"{where}: подпись неполна, нужно «{SIGN} прибор{APART}тракт{APART}где»"]
    tool, tract = parts[0], parts[1]
    faults: list[str] = []
    if tool not in TOOLS:
        faults.append(f"{where}: прибор «{tool}» не из списка {sorted(TOOLS)}")
    if tract not in TRACTS:
        faults.append(f"{where}: тракт «{tract}» не из списка {sorted(TRACTS)}")
    return faults


def main(argv: list[str] | None = None) -> int:
    """Назвать все числа приёмника без подписи прибора и вернуть их числом в коде."""
    parser = argparse.ArgumentParser(description="сторож подписи прибора у чисел приёмника")
    parser.add_argument("path", nargs="?", default=str(ROOT / PROFILES), help="что спрашиваем")
    args = parser.parse_args(argv)
    source = Path(args.path).read_text(encoding="utf-8")
    faults = unsigned(source)
    for fault in faults:
        print(fault)
    print(f"без подписи: {len(faults)}")
    print(f"подписей «{UNNAMED}»: {source.count(UNNAMED)} - это долг замера, а не порядок")
    return 1 if faults else 0


if __name__ == "__main__":
    raise SystemExit(main())
