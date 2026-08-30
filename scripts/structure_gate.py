"""Проверяет раскладку пакетов и названные поимённо скрипты за их пределами."""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Final, NamedTuple

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
    "раздача",
    "окружение",
    "проверка",
    "перевод",
)
#: Шапки, которыми файл целиком снимают с тайпчека.
_MYPY_OFF: Final = re.compile(r"^#\s*mypy:\s*(ignore-errors|disable-error-code)")
#: Шапка, которой файл целиком снимают с линтера; группа - список кодов, если он назван.
_RUFF_OFF: Final = re.compile(r"^#\s*ruff:\s*noqa(?::(?P<codes>.*))?$")
#: Коды ruff про необъявленное имя: ими глушат ровно ту проверку, что ловит `globals()`.
_NAME_CHECKS: Final = frozenset({"F821", "F822"})
#: Ручки, которыми модуль достаёт зависимость по СТРОКЕ с именем. Правило слоёв читает
#: граф импортов, а строку прочитать нечем: `module("torrcast.adapters.chromecast.cast")` из
#: сценария выглядит для гейта чистым, хотя это ровно тот импорт адаптера, который запрещён.
#: Отсюда отдельное правило: внутри слоёв зависимость называется импортом и только им.
DYNAMIC_IMPORTS: Final = frozenset({"module", "legacy_namespace", "import_module", "__import__"})
#: Слои, где `Any` в договоре считается разменом. `adapters` сюда не входит намеренно:
#: там договор держит чужая библиотека, а не мы (см. `_trade_violations`).
TYPED_LAYERS: Final = frozenset({"domain", "ports", "usecases", "cli", "runtime"})
#: Дома, откуда `Any` и `TypeAlias` приезжают под любым именем: `from typing import Any as A`.
TYPING_HOMES: Final = frozenset({"typing", "typing_extensions"})
LAYERS: Final = frozenset({"domain", "ports", "usecases", "adapters", "cli", "runtime"})


class Boundary(NamedTuple):
    """Скрипт под мерой гейта и то, чем он сегодня отличается от модуля пакета."""

    #: Зеркальный тест: у скрипта он назван поимённо, потому что имя файла ему не мать.
    mirror: str
    #: Сколько в нём строк сегодня. Больше - нарушение.
    lines: int
    #: Сколько в нём публичных единиц сегодня. Больше - нарушение.
    units: int


#: Граница обхода DPI, названная поимённо: он живёт скриптом, а не модулем пакета.
#: `sni-shim.py` поднимается службой из `install.sh`, и часть каталога достижима только
#: через него, поэтому мерить его нечем нельзя. Слоя у скрипта нет и быть не может -
#: правила про слои, договор и ввод-вывод к нему неприложимы, - а докстрока, зеркало,
#: глушители, зависимость строкой и чтение окружения на импорте спрашиваются с него
#: наравне с пакетом. Имя файла тоже не спрашивается: у скрипта оно имя команды, и
#: связано со строкой запуска службы, а не с единицей внутри.
#: `lines` и `units` - долг, названный числом: столько их сегодня, и вырасти им нельзя.
#: Свести долг к пакетным порогам (200 строк, одна публичная единица) значит разрезать
#: работающий обход DPI, а это отдельная работа, а не правка заодно.
SCRIPTS: Final = {
    "scripts/sni-shim.py": Boundary(mirror="tests/test_shim.py", lines=1182, units=12),
}
ALLOWED: Final = {
    "domain": frozenset({"domain"}),
    "ports": frozenset({"domain", "ports"}),
    "usecases": frozenset({"domain", "ports", "usecases"}),
    "adapters": frozenset({"domain", "ports", "adapters"}),
    "cli": frozenset({"domain", "ports", "usecases", "cli"}),
    "runtime": LAYERS,
    # Скрипт стоит снаружи раскладки и зовёт пакет так же, как композиционный корень.
    "скрипт": LAYERS,
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
    package_paths = [*(root / "torrcast").rglob("*.py"), *(root / "tgbot").rglob("*.py")]
    for path in sorted(package_paths):
        relative_path = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        parts = relative_path.parts
        layer = (
            parts[1]
            if parts[0] == "torrcast" and len(parts) > 2 and parts[1] in LAYERS
            else "не разложено"
        )
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
    for relative in sorted(SCRIPTS):
        path = root / relative
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        result.append(
            Module(
                path,
                relative,
                _module_name(Path(relative)),
                "скрипт",
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
    if module.layer in {"adapters", "не разложено", "скрипт"}:
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


def _environment_violations(module: Module) -> list[Violation]:
    """Ищет ручки настройки, прочитанные в момент импорта модуля.

    Значение, взятое из окружения на верхнем уровне, застывает на всю жизнь процесса:
    оно такое, каким было у того, кто первым затащил модуль. Ручку показа ставят юниту
    (`--setenv`), а модуль к этому времени давно импортирован, поэтому прочитанная на
    импорте ручка молча не работает. Тест такую ручку тоже не поставит: `monkeypatch.setenv`
    в чужой уже случившийся импорт не попадает, и вместо довода в пробе появляется подмена
    модульного имени - ровно то, чем и держатся россыпи подмен.

    Место, где ручку можно назвать доводом, - вызов, а не шапка файла. Тело функции
    поэтому не считается вовсе, а шапка модуля, тело класса, украшение и умолчание
    параметра - считаются: всё это исполняется на импорте.
    """
    if module.layer == "не разложено":
        return []
    inside: set[int] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            statements: list[ast.AST] = list(node.body)
        elif isinstance(node, ast.Lambda):
            statements = [node.body]
        else:
            continue
        for statement in statements:
            inside.update(id(child) for child in ast.walk(statement))
    failures: list[Violation] = []
    for node in ast.walk(module.tree):
        if id(node) in inside:
            continue
        if isinstance(node, ast.Call):
            named = ast.unparse(node.func)
        elif isinstance(node, ast.Subscript):
            named = ast.unparse(node.value)
        else:
            continue
        head, _, last = named.rpartition(".")
        if last == "getenv" or named.endswith("environ") or head.endswith("environ"):
            failures.append(
                Violation(
                    "окружение",
                    module.relative,
                    node.lineno,
                    f"ручка читается на импорте: {ast.unparse(node)[:60]}",
                )
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


def _local_names(tree: ast.Module, wanted: str) -> frozenset[str]:
    """Имена, которыми в ЭТОМ модуле назван `typing.<wanted>`.

    Мера обязана читать смысл имени, а не его буквы. `from typing import Any as A` с
    последующим `HlsServer: A` разменивает договор ровно так же, как голое `Any`, но по
    буквальному имени не находится: одной строкой импорта правило покупалось бы целиком -
    ровно тем же приёмом, каким когда-то покупались `слои` и `циклы`. Поэтому имя ищется
    по объявлению: сюда попадает и `Any as A`, и цепочка псевдонимов `B = A`, `C = B`,
    объявленная где угодно, включая `if TYPE_CHECKING:` и `try/except ImportError`.

    Само `wanted` в списке всегда: строковую аннотацию `-> "Any"` пишут и там, где импорта
    в файле нет вовсе. Полное имя (`typing.Any`, `t.Any` после `import typing as t`)
    ловится не тут, а по последней части имени в `_mentions_any` и `_is_alias`.

    Имена собираются по всему файлу, без оглядки на вложенность: если внутри модуля имя
    хоть где-то значит `Any`, мера считает его таким везде. Это намеренно щедро - мера
    ошибается в сторону «договор не назван», а не в сторону зелёного счётчика.
    """
    names = {wanted}
    chains: list[tuple[list[str], ast.expr]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").split(".")[0] in TYPING_HOMES:
            names.update(alias.asname or alias.name for alias in node.names if alias.name == wanted)
        elif isinstance(node, ast.Assign):
            chains.append(
                ([item.id for item in node.targets if isinstance(item, ast.Name)], node.value)
            )
        elif (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.value is not None
        ):
            chains.append(([node.target.id], node.value))
    growing = True
    while growing:
        growing = False
        for targets, value in chains:
            named = isinstance(value, ast.Name) and value.id in names
            full = isinstance(value, ast.Attribute) and value.attr == wanted
            if (named or full) and not set(targets) <= names:
                names.update(targets)
                growing = True
    return frozenset(names)


def _mentions_any(node: ast.expr | None, names: frozenset[str], *, typed: bool = True) -> bool:
    """Правда ли внутри выражения типа где-то стоит `Any`, хоть на самом дне.

    Смотрится вглубь, а не по верхнему имени: `Callable[..., Any]`, `dict[str, Any]` и
    `Any | None` разменивают договор ровно так же, как голое `Any`. Имя берётся не
    буквой, а списком `names` из объявлений модуля (`_local_names`), так что `Слот: A`
    после `from typing import Any as A` считается наравне с голым. Полное имя ловится по
    последней части: `typing.Any` и `t.Any` - тот же размен.

    Строковая запись разбирается тем же разбором - иначе правило покупалось бы кавычками,
    а гейт, купленный строкой, у нас уже был, - но только там, где строка и правда
    означает тип (`typed`). В обычном присваивании строка это данные: `"Any"` в `__all__`
    называет реэкспорт имени, а не размен договора.
    """
    if node is None:
        return False
    for inner in ast.walk(node):
        if isinstance(inner, ast.Name) and inner.id in names:
            return True
        if isinstance(inner, ast.Attribute) and inner.attr == "Any":
            return True
        if typed and isinstance(inner, ast.Constant) and isinstance(inner.value, str):
            try:
                quoted = ast.parse(inner.value, mode="eval").body
            except SyntaxError:
                continue
            if _mentions_any(quoted, names):
                return True
    return False


def _is_alias(node: ast.expr | None, names: frozenset[str]) -> bool:
    """Правда ли это пометка `TypeAlias`: у неё договор лежит не в аннотации, а в значении.

    Имя пометки берётся из объявлений модуля по той же причине, что и имя `Any`: иначе
    `from typing import TypeAlias as TA` увело бы `RawRow: TA = Any` мимо меры - значение
    псевдонима читалось бы как обычная аннотация, которой `Any` не назван.
    """
    if isinstance(node, ast.Name):
        return node.id in names
    return isinstance(node, ast.Attribute) and node.attr == "TypeAlias"


def _contract_sites(
    body: list[ast.stmt], owner: str, names: frozenset[str], aliases: frozenset[str]
) -> Iterator[tuple[int, str, str]]:
    """Обходит объявленный договор модуля и отдаёт места, где он назван `Any`.

    Договор - это то, что видно снаружи тела: слоты модуля, поля классов, псевдонимы имён
    и подписи единиц. В тела функций обход не заходит: локальная переменная договором ни
    для кого не является, и `Any` там - дело одного места. Зато заходит внутрь
    `if TYPE_CHECKING:` и `try/except ImportError`, потому что объявление оттуда тайпчек
    читает наравне с голым, а спрятать за таким `if` можно что угодно.
    """
    for node in body:
        if isinstance(node, ast.If):
            yield from _contract_sites(node.body, owner, names, aliases)
            yield from _contract_sites(node.orelse, owner, names, aliases)
        elif isinstance(node, ast.Try):
            for branch in (node.body, node.orelse, node.finalbody):
                yield from _contract_sites(branch, owner, names, aliases)
            for handler in node.handlers:
                yield from _contract_sites(handler.body, owner, names, aliases)
        elif isinstance(node, ast.ClassDef):
            yield from _contract_sites(node.body, f"{owner}{node.name}.", names, aliases)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            arguments = node.args
            named = [
                *arguments.posonlyargs,
                *arguments.args,
                *arguments.kwonlyargs,
                *(item for item in (arguments.vararg, arguments.kwarg) if item is not None),
            ]
            for argument in named:
                if _mentions_any(argument.annotation, names):
                    yield (
                        argument.lineno,
                        "тип параметра не назван",
                        f"{owner}{node.name}({argument.arg})",
                    )
            if _mentions_any(node.returns, names):
                yield node.lineno, "тип возврата не назван", f"{owner}{node.name}"
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            name = f"{owner}{node.target.id}"
            if _is_alias(node.annotation, aliases):
                if _mentions_any(node.value, names):
                    yield node.lineno, "имя подменено на Any", name
            elif _mentions_any(node.annotation, names):
                what = "тип поля не назван" if owner else "тип слота не назван"
                yield node.lineno, what, f"{name}: {ast.unparse(node.annotation)}"
        elif isinstance(node, ast.Assign) and _mentions_any(node.value, names, typed=False):
            assigned = [target.id for target in node.targets if isinstance(target, ast.Name)]
            for name in assigned:
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

    Имя `Any` в файле может быть любым, и мера берёт его из объявлений модуля
    (`_local_names`), а не из буквы: `from typing import Any as A` не покупает счётчик.
    """
    if module.layer not in TYPED_LAYERS:
        return []
    names = _local_names(module.tree, "Any")
    aliases = _local_names(module.tree, "TypeAlias")
    return [
        Violation("размен", module.relative, line, f"{what}: {name}")
        for line, what, name in _contract_sites(module.tree.body, "", names, aliases)
    ]


def _handout_violations(module: Module, known: set[str]) -> list[Violation]:
    """Ищет пакетный `__init__.py`, который кладёт в свой namespace чужое имя.

    Плоский namespace монолита вычищен, реэкспорты из пакетных `__init__.py` сняты все, и
    две трети из них никто не звал. Отрастает это молча и за две волны: одна строка
    `from .digest import digest` возвращает пакету право раздавать имя, объявленное в его
    подмодуле, и у имени снова два адреса - дом и витрина. Ни одно из прежних правил такой
    строки не считает: правило слоёв её пропускает (пакет зовёт свой же подмодуль), цикла
    она не делает, длины не добавляет, договора не разменивает. Проба это показала: имя,
    подсаженное обратно в `__init__.py`, оставляло гейт нулевым по всем одиннадцати.

    Нарушение - раздача ИМЕНИ: `from .модуль import имя` и `from torrcast.пакет.модуль
    import имя`. Название дома нарушением не является: `import подмодуль` и
    `from . import подмодуль` дают модулю ровно тот адрес, который у него и так есть, а
    второго не заводят.

    Дом признаётся только по форме `from . import подмодуль`, и это не придирка к записи.
    Подмодуль, затенённый собственным `__init__`, домом не является: в пакете
    `torrcast.domain.digest` лежит модуль `digest.py`, поэтому `from torrcast.domain.digest
    import digest` читается как название дома, а имя `digest` в namespace пакета после
    него - функция, а не модуль. Отличить одно от другого по имени модуля нечем, а форма
    `from . import подмодуль` этой двусмысленности не имеет вовсе.

    Псевдоним - тоже раздача, и у обеих записей: `from . import digest as d` и
    `import torrcast.domain.digest as d` заводят модулю второй адрес ровно так же, как
    реэкспорт имени. Иначе правило покупается одним словом `as`.

    Имя из чужого пакета считается наравне со своим: `from pathlib import Path` в
    `__init__.py` кладёт в namespace пакета `Path`, и зовущий берёт его оттуда. Пакетный
    `__init__.py` называет свои дома и не связывает себя больше ничем - `annotations` из
    `__future__` там тоже незачем, потому что аннотаций в нём нет.
    """
    if module.path.name != "__init__.py":
        return []
    failures: list[Violation] = []
    for node in ast.walk(module.tree):
        if isinstance(node, ast.Import):
            failures.extend(
                Violation(
                    "раздача",
                    module.relative,
                    node.lineno,
                    f"второй адрес модулю: {alias.name} as {alias.asname}",
                )
                for alias in node.names
                if alias.asname is not None
            )
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        parts = module.name.split(".")
        base = ".".join(parts[: max(0, len(parts) - node.level + 1)]) if node.level else ""
        source = ".".join(part for part in (base, node.module) if part) or "."
        for alias in node.names:
            if alias.name == "*":
                failures.append(
                    Violation(
                        "раздача", module.relative, node.lineno, f"пакет раздаёт всё из {source}"
                    )
                )
                continue
            own_home = (
                node.level == 1
                and node.module is None
                and alias.asname is None
                and f"{base}.{alias.name}" in known
            )
            if not own_home:
                failures.append(
                    Violation(
                        "раздача",
                        module.relative,
                        node.lineno,
                        f"пакет раздаёт имя {alias.name} из {source}",
                    )
                )
    return failures


def _bound_inside(node: ast.AST) -> frozenset[str]:
    """Имена, которые тест завёл сам: их значение считает он, а не импорт."""
    names: set[str] = set()
    for inner in ast.walk(node):
        if isinstance(inner, ast.arg):
            names.add(inner.arg)
        elif isinstance(inner, ast.Name) and isinstance(inner.ctx, (ast.Store, ast.Del)):
            names.add(inner.id)
        elif isinstance(inner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(inner.name)
        elif isinstance(inner, (ast.Import, ast.ImportFrom)):
            names.update((alias.asname or alias.name).split(".")[0] for alias in inner.names)
    return frozenset(names)


def _only_the_import(node: ast.Assert, local: frozenset[str]) -> bool:
    """Утверждение, которое краснеет ровно на несостоявшемся импорте.

    `X is not None` над именем, которое тест не заводил и ни во что не звал, - это
    утверждение про импорт: значение туда положил `from ... import X`, и другим оно не
    станет. Ни поломку модуля, ни смену его ответа такое не ловит.
    """
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1:
        return False
    right = test.comparators[0]
    if not isinstance(test.ops[0], ast.IsNot) or not isinstance(right, ast.Constant):
        return False
    if right.value is not None or any(isinstance(step, ast.Call) for step in ast.walk(test.left)):
        return False
    named = test.left
    while isinstance(named, ast.Attribute):
        named = named.value
    return isinstance(named, ast.Name) and named.id not in local


def _empty_test_violations(root: Path) -> list[Violation]:
    """Тесты, у которых все утверждения - про импорт.

    Правило `зеркало` требует у модуля файл теста, и существованием файла оно и
    покупается: зеркало есть, счётчик нулевой, а поломку своего модуля такой файл
    пропускает целиком. Предмет тут - весь тест, а не отдельная строка: `assert X is not
    None` рядом с настоящими утверждениями - это лишняя строка, а не купленная зелень.
    """
    found: list[Violation] = []
    for path in sorted((root / "tests").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test"):
                continue
            checks = [step for step in ast.walk(node) if isinstance(step, ast.Assert)]
            local = _bound_inside(node)
            if checks and all(_only_the_import(check, local) for check in checks):
                found.append(
                    Violation(
                        "проверка",
                        path.relative_to(root).as_posix(),
                        node.lineno,
                        f"{node.name} держит только импорт",
                    )
                )
    return found


def _translation_violations(module: Module) -> list[Violation]:
    """Не даёт пользовательской строке обойти языковой каталог прямым выводом."""
    if not module.relative.startswith("tgbot/"):
        return []
    found: list[Violation] = []
    for node in ast.walk(module.tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in {"input", "print"}:
            continue
        for argument in node.args:
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str):
                found.append(
                    Violation(
                        "перевод",
                        module.relative,
                        argument.lineno,
                        f"строка для {node.func.id} миновала языковой каталог",
                    )
                )
    return found


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
        # У скрипта с названной границы пороги - его сегодняшний долг (:data:`SCRIPTS`).
        boundary = SCRIPTS.get(module.relative)
        limit = boundary.lines if boundary else 200
        if module.lines > limit:
            failures.append(
                Violation(
                    "длина", module.relative, limit + 1, f"{module.lines} строк, порог {limit}"
                )
            )
        units = _public_units(module.tree)
        allowed = boundary.units if boundary else 1
        if len(units) > allowed:
            failures.append(
                Violation(
                    "единица",
                    module.relative,
                    units[allowed].lineno,
                    f"публичных единиц: {len(units)}, порог {allowed}",
                )
            )
        # Имя файла скрипта - имя команды: оно связано со строкой запуска службы,
        # а не с единицей внутри, и переименовать его заодно нечем.
        if len(units) == 1 and module.path.name != "__init__.py" and boundary is None:
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
                root / boundary.mirror
                if boundary
                else root
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
        failures.extend(_environment_violations(module))
        failures.extend(_trade_violations(module))
        failures.extend(_handout_violations(module, known))
        failures.extend(_translation_violations(module))
        edges[module.name] = {
            target
            for name, _line in imports
            if (target := _target_module(name, known)) is not None and target != module.name
        }
    failures.extend(_cycle_violations(modules, edges))
    failures.extend(_empty_test_violations(root))
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
