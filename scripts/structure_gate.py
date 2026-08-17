"""Проверяет соответствие пакета torrcast целевой слоистой структуре."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final

RULES: Final = (
    "длина",
    "единица",
    "имя",
    "слои",
    "циклы",
    "докстрока",
    "зеркало",
    "ввод-вывод",
    "обход",
    "глушитель",
    "размен",
)
#: Шапки, которыми файл целиком снимают с тайпчека.
_MYPY_OFF: Final = re.compile(r"^#\s*mypy:\s*(ignore-errors|disable-error-code)")
#: Шапка, которой файл целиком снимают с линтера; группа - список кодов, если он назван.
_RUFF_OFF: Final = re.compile(r"^#\s*ruff:\s*noqa(?::(?P<codes>.*))?$")
#: Коды ruff про необъявленное имя: ими глушат ровно ту проверку, что ловит `globals()`.
_NAME_CHECKS: Final = frozenset({"F821", "F822"})
#: Ручки, которыми модуль достаёт зависимость по СТРОКЕ с именем. Правило слоёв читает
#: граф импортов, а строку прочитать нечем: `module("torrcast.cast")` из сценария
#: выглядит для гейта чистым, хотя это ровно тот импорт адаптера, который запрещён.
#: Отсюда отдельное правило: внутри слоёв зависимость называется импортом и только им.
DYNAMIC_IMPORTS: Final = frozenset({"module", "legacy_namespace", "import_module", "__import__"})
#: Слои, где `Any` в договоре считается разменом. `adapters` сюда не входит намеренно:
#: там договор держит чужая библиотека, а не мы (см. `_trade_violations`).
TYPED_LAYERS: Final = frozenset({"domain", "ports", "usecases", "cli", "runtime"})
LAYERS: Final = frozenset({"domain", "ports", "usecases", "adapters", "cli", "runtime"})
ALLOWED: Final = {
    "domain": frozenset({"domain"}),
    "ports": frozenset({"domain", "ports"}),
    "usecases": frozenset({"domain", "ports", "usecases"}),
    "adapters": frozenset({"domain", "ports", "adapters"}),
    "cli": frozenset({"domain", "ports", "usecases", "cli"}),
    "runtime": LAYERS,
}
BANNED_IO: Final = frozenset(
    {
        "requests",
        "urllib",
        "socket",
        "subprocess",
        "http",
        "shutil",
        "tempfile",
        "pychromecast",
        "zeroconf",
    }
)


@dataclass(frozen=True)
class Violation:
    """Одно нарушение правила структуры."""

    rule: str
    path: str
    line: int
    message: str


@dataclass(frozen=True)
class Module:
    """Разобранный модуль с метаданными о его месте в пакете."""

    path: Path
    relative: str
    name: str
    layer: str
    tree: ast.Module
    lines: int


def _module_name(relative: Path) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _load_modules(root: Path) -> list[Module]:
    result: list[Module] = []
    for path in sorted((root / "torrcast").rglob("*.py")):
        relative_path = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        parts = relative_path.parts
        layer = parts[1] if len(parts) > 2 and parts[1] in LAYERS else "не разложено"
        result.append(
            Module(
                path,
                relative_path.as_posix(),
                _module_name(relative_path),
                layer,
                ast.parse(source, filename=str(path)),
                len(source.splitlines()),
            )
        )
    return result


def _snake_case(name: str) -> str:
    first = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    return re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", first).lower()


def _public_units(tree: ast.Module) -> list[ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef]:
    return [
        node
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and not node.name.startswith("_")
    ]


def _imports(module: Module) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    package = module.name.rsplit(".", 1)[0] if module.path.name != "__init__.py" else module.name
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            found.extend((alias.name, node.lineno) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".")
                keep = max(0, len(base) - node.level + 1)
                prefix = base[:keep]
                name = ".".join(prefix + ([node.module] if node.module else []))
            else:
                name = node.module or ""
            if (
                name.startswith("torrcast")
                and all(alias.name != "*" for alias in node.names)
                and (name.count(".") == 0 or (node.level and node.module is None))
            ):
                # ``from torrcast import legacy`` зависит от дочернего модуля,
                # а ``from torrcast.foo import Name`` - от самого ``torrcast.foo``.
                found.extend((f"{name}.{alias.name}", node.lineno) for alias in node.names)
                continue
            found.append((name, node.lineno))
    return found


def _target_module(name: str, known: set[str]) -> str | None:
    candidate = name
    while candidate:
        if candidate in known:
            return candidate
        candidate = candidate.rpartition(".")[0]
    return None


def _layer_violations(module: Module, imports: list[tuple[str, int]]) -> list[Violation]:
    failures: list[Violation] = []
    for name, line in imports:
        if not name.startswith("torrcast."):
            continue
        parts = name.split(".")
        imported_layer = parts[1] if len(parts) > 2 and parts[1] in LAYERS else "не разложено"
        if module.layer != "не разложено" and (
            imported_layer == "не разложено" or imported_layer not in ALLOWED[module.layer]
        ):
            failures.append(
                Violation("слои", module.relative, line, f"слой {module.layer} импортирует {name}")
            )
    if module.relative == "torrcast/__init__.py":
        for index, node in enumerate(module.tree.body):
            docstring = (
                index == 0
                and isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            )
            export_assignment = isinstance(node, (ast.Assign, ast.AnnAssign)) and any(
                isinstance(target, ast.Name) and target.id == "__all__"
                for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
            )
            if not (
                docstring or export_assignment or isinstance(node, (ast.Import, ast.ImportFrom))
            ):
                failures.append(
                    Violation(
                        "слои",
                        module.relative,
                        node.lineno,
                        "корневой __init__.py должен только реэкспортировать",
                    )
                )
    return failures


def _io_violations(module: Module, imports: list[tuple[str, int]]) -> list[Violation]:
    if module.layer in {"adapters", "не разложено"}:
        return []
    failures: list[Violation] = []
    aliases: dict[str, str] = {}
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[alias.asname or alias.name.split(".")[0]] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = f"{node.module}.{alias.name}"
    for name, line in imports:
        if name.split(".")[0] in BANNED_IO:
            failures.append(
                Violation(
                    "ввод-вывод", module.relative, line, f"прямой импорт ввода-вывода: {name}"
                )
            )
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        call = ast.unparse(node.func)
        expanded = (
            aliases.get(call.split(".")[0], call.split(".")[0]) + call[len(call.split(".")[0]) :]
        )
        if call == "open" or expanded == "builtins.open":
            failures.append(
                Violation("ввод-вывод", module.relative, node.lineno, "прямой вызов open")
            )
        elif expanded == "time.sleep":
            failures.append(
                Violation("ввод-вывод", module.relative, node.lineno, "прямой вызов time.sleep")
            )
    return failures


def _bypass_violations(module: Module) -> list[Violation]:
    """Ищет зависимости, названные строкой в обход правила слоёв.

    Разложенному модулю разрешён ровно один способ назвать чужой символ - импорт.
    Строка с именем модуля обходит и гейт, и mypy, а `globals().update` довершает дело:
    имя появляется в модуле ниоткуда, читатель ищет его глазами по всему пакету, а
    `.pyi` рядом врёт компилятору, что имя объявлено честно.
    """
    if module.layer == "не разложено":
        return []
    failures: list[Violation] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call):
            continue
        call = ast.unparse(node.func)
        if call.rpartition(".")[2] in DYNAMIC_IMPORTS:
            failures.append(
                Violation("обход", module.relative, node.lineno, f"зависимость строкой: {call}")
            )
        elif call in {"globals().update", "vars().update"}:
            failures.append(
                Violation("обход", module.relative, node.lineno, "имена вписываются в globals")
            )
    # Заглушка рядом с `__init__.py` - такая же ложь компилятору, как и рядом с обычным
    # модулем, и по объёму крупнейшая в пакете: `torrcast/cli/__init__.pyi` объявляет 736
    # строк имён, которых в самом `__init__.py` нет. Исключение для `__init__` тут
    # держалось не по смыслу, а потому что правило писалось на примере одного файла.
    stub = module.path.with_suffix(".pyi")
    if stub.exists():
        failures.append(
            Violation("обход", module.relative, 1, f"заглушка вместо честных имён: {stub.name}")
        )
    return failures


def _silencer_violations(module: Module) -> list[Violation]:
    """Ищет файлы, где проверку выключили целиком, а не разобрались с местом.

    `mypy --strict` и `ruff check` зелены ровно настолько, насколько им дали смотреть.
    Строка `# mypy: ignore-errors` в шапке снимает тайпчек со всего файла, `# ruff: noqa`
    - все правила линтера, а `# ruff: noqa: F821, F822` бьёт прицельно по «имя не
    объявлено» - то есть по единственной проверке, которая ловит имена, вписанные в
    модуль через `globals().update`. Такой глушитель не оставляет следа ни в одном
    отчёте: файл выглядит проверенным.
    """
    if module.layer == "не разложено":
        return []
    failures: list[Violation] = []
    source = module.path.read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(source, start=1):
        text = line.strip()
        if not text.startswith("#"):
            continue
        if _MYPY_OFF.match(text):
            failures.append(
                Violation("глушитель", module.relative, number, f"тайпчек выключен: {text}")
            )
        elif (found := _RUFF_OFF.match(text)) is not None:
            codes = found.group("codes") or ""
            hidden = {code.strip() for code in codes.split(",") if code.strip()}
            if not hidden or hidden & _NAME_CHECKS:
                failures.append(
                    Violation("глушитель", module.relative, number, f"линтер выключен: {text}")
                )
    return failures


def _mentions_any(node: ast.expr | None, *, typed: bool = True) -> bool:
    """Правда ли внутри выражения типа где-то стоит `Any`, хоть на самом дне.

    Смотрится вглубь, а не по верхнему имени: `Callable[..., Any]`, `dict[str, Any]` и
    `Any | None` разменивают договор ровно так же, как голое `Any`. Строковая запись
    разбирается тем же разбором - иначе правило покупалось бы кавычками, а гейт,
    купленный строкой, у нас уже был, - но только там, где строка и правда означает тип
    (`typed`). В обычном присваивании строка это данные: `"Any"` в `__all__` называет
    реэкспорт имени, а не размен договора.
    """
    if node is None:
        return False
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id == "Any":
            return True
        if isinstance(inner, ast.Attribute) and inner.attr == "Any":
            return True
        if typed and isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            try:
                quoted = ast.parse(inner.value, mode="eval").body
            except SyntaxError:
                continue
            if _mentions_any(quoted):
                return True
    return False


def _is_alias(node: ast.expr | None) -> bool:
    """Правда ли это пометка `TypeAlias`: у неё договор лежит не в аннотации, а в значении."""
    if isinstance(node, ast.Name):
        return node.id == "TypeAlias"
    return isinstance(node, ast.Attribute) and node.attr == "TypeAlias"


def _contract_sites(body: list[ast.stmt], owner: str) -> Iterator[tuple[int, str, str]]:
    """Обходит объявленный договор модуля и отдаёт места, где он назван `Any`.

    Договор - это то, что видно снаружи тела: слоты модуля, поля классов, псевдонимы имён
    и подписи единиц. В тела функций обход не заходит: локальная переменная договором ни
    для кого не является, и `Any` там - дело одного места. Зато заходит внутрь
    `if TYPE_CHECKING:` и `try/except ImportError`, потому что объявление оттуда тайпчек
    читает наравне с голым, а спрятать за таким `if` можно что угодно.
    """
    for node in body:
        if isinstance(node, ast.If):
            yield from _contract_sites(node.body, owner)
            yield from _contract_sites(node.orelse, owner)
        elif isinstance(node, ast.Try):
            for branch in (node.body, node.orelse, node.finalbody):
                yield from _contract_sites(branch, owner)
            for handler in node.handlers:
                yield from _contract_sites(handler.body, owner)
        elif isinstance(node, ast.ClassDef):
            yield from _contract_sites(node.body, f"{owner}{node.name}.")
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            named = [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                *(item for item in (arguments.vararg, arguments.kwarg) if item is not None),
            ]
            for argument in named:
                if _mentions_any(argument.annotation):
                    yield (
                        argument.lineno,
                        "тип параметра не назван",
                        f"{owner}{node.name}({argument.arg})",
                    )
            if _mentions_any(node.returns):
                yield node.lineno, "тип возврата не назван", f"{owner}{node.name}"
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = f"{owner}{node.target.id}"
            if _is_alias(node.annotation):
                if _mentions_any(node.value):
                    yield node.lineno, "имя подменено на Any", name
            elif _mentions_any(node.annotation):
                what = "тип поля не назван" if owner else "тип слота не назван"
                yield node.lineno, what, f"{name}: {ast.unparse(node.annotation)}"
        elif isinstance(node, ast.Assign) and _mentions_any(node.value, typed=False):
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            for name in names:
                yield node.lineno, "имя подменено на Any", f"{owner}{name}"


def _trade_violations(module: Module) -> list[Violation]:
    """Ищет договор, размененный на `Any` там, где его обязаны были назвать.

    Правило слоёв читает импорты, а `Any` импорта не требует: если зависимость увести из
    строки с именем модуля в слот композиционного корня, счётчик `обход` падает, а имя
    класса адаптера слою всё равно не назвать - и слот объявляют `Any`. Договора не стало
    ни на грамм больше, но ни одно из прежних правил этого не считает: `HlsServer: Any` в
    сценарии для гейта выглядит честным объявлением, а для mypy - разрешением на всё.
    Поэтому размен считается отдельно, как и любой другой способ убрать проверку.

    Считается только объявленный ДОГОВОР: слоты модуля, псевдонимы имён, поля классов и
    протоколов, параметры и возвраты единиц. Внутрь тел правило не смотрит - локальная
    переменная договором не является. Приватное имя от публичного тут не отличается: в
    слое сценариев `_recoder` зовут из соседних модулей и он назван в `__all__`, так что
    его подпись - такой же договор, как у любой публичной единицы.

    Законный `Any` ровно один, и он вынесен целым слоем: `adapters`. Там договор держит
    не пакет, а чужая библиотека - ответ ffprobe, JSON индексера, объект pychromecast, -
    и назвать её типы честнее нечем; ради этой границы адаптеры и заведены. Всё, что
    приехало через границу дальше в слои, обязано быть уже названным. Нераскладанные
    файлы пропускаются наравне с правилами `обход` и `глушитель`: это старые фасады под
    снос, их считают волнами разреза, а не этой мерой.
    """
    if module.layer not in TYPED_LAYERS:
        return []
    return [
        Violation("размен", module.relative, line, f"{what}: {name}")
        for line, what, name in _contract_sites(module.tree.body, "")
    ]


def _cycle_violations(modules: list[Module], edges: dict[str, set[str]]) -> list[Violation]:
    by_name = {module.name: module for module in modules}
    failures: list[Violation] = []
    visiting: list[str] = []
    done: set[str] = set()

    def visit(name: str) -> None:
        if name in done:
            return
        if name in visiting:
            cycle = [*visiting[visiting.index(name) :], name]
            module = by_name[name]
            message = "цикл импортов: " + " -> ".join(cycle)
            if not any(item.rule == "циклы" and item.message == message for item in failures):
                failures.append(Violation("циклы", module.relative, 1, message))
            return
        visiting.append(name)
        for target in sorted(edges.get(name, set())):
            visit(target)
        visiting.pop()
        done.add(name)

    for name in sorted(by_name):
        visit(name)
    return failures


def check(root: Path) -> list[Violation]:
    """Возвращает все нарушения структуры внутри корня репозитория."""
    modules = _load_modules(root)
    known = {module.name for module in modules}
    edges: dict[str, set[str]] = {}
    failures: list[Violation] = []
    for module in modules:
        if module.lines > 200:
            failures.append(
                Violation("длина", module.relative, 201, f"{module.lines} строк, порог 200")
            )
        units = _public_units(module.tree)
        if len(units) > 1:
            failures.append(
                Violation(
                    "единица", module.relative, units[1].lineno, f"публичных единиц: {len(units)}"
                )
            )
        if len(units) == 1 and module.path.name != "__init__.py":
            expected = _snake_case(units[0].name) + ".py"
            if module.path.name != expected:
                failures.append(
                    Violation(
                        "имя",
                        module.relative,
                        units[0].lineno,
                        f"для {units[0].name} ожидается {expected}",
                    )
                )
        if ast.get_docstring(module.tree, clean=False) is None:
            failures.append(Violation("докстрока", module.relative, 1, "нет докстроки модуля"))
        if module.path.name != "__init__.py":
            mirror = (
                root
                / "tests"
                / Path(*Path(module.relative).parts[1:]).with_name(f"test_{module.path.name}")
            )
            if not mirror.exists():
                failures.append(
                    Violation(
                        "зеркало", module.relative, 1, f"нет {mirror.relative_to(root).as_posix()}"
                    )
                )
        imports = _imports(module)
        failures.extend(_layer_violations(module, imports))
        failures.extend(_io_violations(module, imports))
        failures.extend(_bypass_violations(module))
        failures.extend(_silencer_violations(module))
        failures.extend(_trade_violations(module))
        edges[module.name] = {
            target
            for name, _line in imports
            if (target := _target_module(name, known)) is not None and target != module.name
        }
    failures.extend(_cycle_violations(modules, edges))
    order = {rule: index for index, rule in enumerate(RULES)}
    return sorted(failures, key=lambda item: (order[item.rule], item.path, item.line, item.message))


def report(violations: Iterable[Violation]) -> None:
    """Печатает ограниченный по размеру человекочитаемый отчёт."""
    items = list(violations)
    counts = Counter(item.rule for item in items)
    print("Сводка нарушений:")
    for rule in RULES:
        print(f"{rule} — {counts[rule]}")
    print("\nНарушения:")
    for rule in RULES:
        group = [item for item in items if item.rule == rule]
        for item in group[:10]:
            print(f"{item.path}:{item.line} — [{item.rule}] {item.message}")
        if len(group) > 10:
            print(f"[{rule}] и ещё {len(group) - 10}")
    if not items:
        print("нет")


def main(argv: list[str] | None = None) -> int:
    """Запускает гейт в режиме отчёта или строгом режиме с ошибкой."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", type=Path, default=Path.cwd())
    parser.add_argument("--strict", action="store_true")
    arguments = parser.parse_args(argv)
    violations = check(arguments.root.resolve())
    report(violations)
    return int(arguments.strict and bool(violations))


if __name__ == "__main__":
    sys.exit(main())
