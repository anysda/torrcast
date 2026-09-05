"""Перепись мест речи в сценариях и точная замена надписи в исходнике.

Место речи - это ВЫЗОВ СТОКА, содержащий ``phrase(...)``, а не отдельный ``print``.
Речь уходит человеку не только печатью: её несут ``progress.note``, ``state._say`` и
колбэки ``say=``/``log=``, которые сценарий получает снаружи. Считать по ``print`` значит
недосчитаться каждого шестого места.

Единицей взят сток, а не ``phrase``: одна надпись бывает склеена из двух ключей, и
сторожить её надо целиком - ровно так, как её читает человек.
"""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeGuard

#: Чем сценарий отдаёт надпись человеку. Имена, а не типы: сток приходит и параметром
#: (``say=``, ``log=``), и методом состояния (``state._say``), и общее у них только имя.
SINKS: Final = frozenset({"print", "say", "log", "warn", "_say", "note"})

#: Где ищем. Домен и адаптеры сюда не входят намеренно: решение, о котором надо сказать
#: человеку, принимает сценарий, и охрана нужна там, где принято решение.
SPEECH_ROOT: Final = Path("torrcast") / "usecases"


@dataclass(frozen=True, slots=True)
class Span:
    """Кусок исходника по разбору: строки с единицы, колонки в БАЙТАХ utf-8."""

    line: int
    col: int
    end_line: int
    end_col: int

    def contains(self, other: Span) -> bool:
        return (self.line, self.col) <= (other.line, other.col) and (
            other.end_line,
            other.end_col,
        ) <= (self.end_line, self.end_col)


@dataclass(frozen=True, slots=True)
class Site:
    """Одно место речи: где стоит, чем говорит и какие ключи произносит."""

    path: str
    sink: str
    keys: tuple[str, ...]
    span: Span
    phrases: tuple[Span, ...]

    @property
    def where(self) -> str:
        return f"{self.path}:{self.span.line}"


def _is_phrase(node: ast.AST) -> TypeGuard[ast.Call]:
    if not isinstance(node, ast.Call):
        return False
    func = node.func
    if isinstance(func, ast.Name):
        return func.id == "phrase"
    return isinstance(func, ast.Attribute) and func.attr == "phrase"


def _sink_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id if func.id in SINKS else None
    if isinstance(func, ast.Attribute) and func.attr in SINKS:
        base = func.value
        if isinstance(base, ast.Name):
            return f"{base.id}.{func.attr}"
        if isinstance(base, ast.Attribute):
            return f"{base.attr}.{func.attr}"
        return f"?.{func.attr}"
    return None


def _span(node: ast.expr) -> Span:
    assert node.end_lineno is not None and node.end_col_offset is not None
    return Span(node.lineno, node.col_offset, node.end_lineno, node.end_col_offset)


def _outermost(spans: tuple[Span, ...]) -> tuple[Span, ...]:
    """Только внешние: вложенный ``phrase`` внутри ``phrase`` порвал бы склейку."""
    return tuple(s for s in spans if not any(o is not s and o.contains(s) for o in spans))


def sites(root: Path) -> list[Site]:
    """Все места речи под ``root`` в порядке файлов и строк."""
    found: list[Site] = []
    for path in sorted((root / SPEECH_ROOT).rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _is_phrase(node):
                continue
            sink = _sink_name(node)
            if sink is None:
                continue
            spoken = [inner for inner in ast.walk(node) if _is_phrase(inner)]
            if not spoken:
                continue
            keys = tuple(
                str(call.args[0].value)
                for call in spoken
                if call.args and isinstance(call.args[0], ast.Constant)
            )
            found.append(
                Site(
                    path=str(path.relative_to(root)),
                    sink=sink,
                    keys=keys,
                    span=_span(node),
                    phrases=_outermost(tuple(_span(call) for call in spoken)),
                )
            )
    return [site for site in found if not _nested(site, found)]


def _nested(site: Site, among: list[Site]) -> bool:
    """Сток внутри стока считается один раз, по внешнему: иначе место двоится."""
    return any(
        other is not site and other.path == site.path and other.span.contains(site.span)
        for other in among
    )


def fingerprint(found: list[Site]) -> str:
    """Отпечаток переписи: им карта досягаемости доказывает, что снята с ЭТОГО дерева.

    Без отпечатка вчерашняя карта читалась бы как сегодняшняя: строки уехали, места
    сошлись по номерам не с теми, и сторож померил бы вчерашнее дерево, ничего не заметив.
    """
    payload = json.dumps(
        [[s.path, s.span.line, s.span.col, s.sink, list(s.keys)] for s in found],
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


def _offset(text: str, line: int, col: int) -> int:
    lines = text.splitlines(keepends=True)
    head = "".join(lines[: line - 1])
    return len(head) + len(lines[line - 1].encode()[:col].decode(errors="ignore"))


def mutated(text: str, site: Site) -> str:
    """Исходник, в котором надписи этого места заменены литералом ``"MUT"``.

    Замена точная, по колонкам разбора, и идёт с конца: правка ранней строки сдвинула бы
    смещения поздних, и склейка порвала бы сама себя.
    """
    for span in sorted(site.phrases, key=lambda s: (s.line, s.col), reverse=True):
        start = _offset(text, span.line, span.col)
        end = _offset(text, span.end_line, span.end_col)
        text = text[:start] + '"MUT"' + text[end:]
    return text
