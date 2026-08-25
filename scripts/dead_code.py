"""Мёртвый код в большом: три стадии, и охват у каждой - это и есть её смысл.

1. Имя без единого вызывающего в пакете и в инструментах. Тесты в охват НЕ входят
   намеренно: единственным вызывающим мертвеца часто оказывается его же зеркальный тест,
   и тогда мертвец удаляется вместе с тестом, а не хранится ради него. `scripts` в охвате
   наоборот обязаны быть: стенды и пробы - законные вызывающие продукта, наравне с
   командой `cast`, и без них живой код читается мёртвым.
2. Имя без вызывающих в тестах. Охват тут ВЕСЬ, включая пакет, иначе подделка договора
   выглядит мёртвой: зовёт её сценарий, а он был бы за границей охвата. Предмет стадии
   при этом только `tests` - находки пакета разбирает стадия 1.
3. Модуль пакета, которого не импортирует никто. `vulture` считает ИМЕНА, а не модули, и
   на разрезе с зеркальными именами слепнет: пока в дереве живёт хоть один `Feed`,
   объявление `Feed` в мёртвом соседнем модуле читается как живое. Ловится это графом
   импортов: модуль жив, если до него есть путь от корня.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterable, Iterator
from pathlib import Path

import grimp

REPO = Path(__file__).resolve().parent.parent
PACKAGE = "torrcast"
#: Живое, что зовут не из питона: кто именно зовёт - сказано у каждой строки внутри.
WHITELIST = "vulture-whitelist.py"
#: Имя модуля в чужом тексте: `torrcast.domain.warm_settings`, `torrcast.usecases.doctor`.
MENTION = re.compile(r"\btorrcast(?:\.[a-z_][a-z0-9_]*)+")


def _entry_points(pyproject: Path) -> Iterator[str]:
    """Точки входа из `[project.scripts]`: команду `cast` зовёт оболочка, не питон."""
    scripts = tomllib.loads(pyproject.read_text())["project"]["scripts"]
    for target in scripts.values():
        yield str(target).split(":", 1)[0]


def _imported_by(source: Path) -> Iterator[str]:
    """Имена пакета, которые импортирует один файл-инструмент."""
    for node in ast.walk(ast.parse(source.read_text(), str(source))):
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            yield node.module
            yield from (f"{node.module}.{alias.name}" for alias in node.names)


def _mentioned_in(source: Path) -> Iterator[str]:
    """Имена пакета, названные строкой: `python -c 'from torrcast...'`, конфиг, оболочка."""
    yield from MENTION.findall(source.read_text(errors="ignore"))


def _named(modules: set[str], candidates: Iterable[str]) -> set[str]:
    """Оставить от названного то, что и правда модуль: `пакет.модуль.ИМЯ` - это модуль."""
    found: set[str] = set()
    for candidate in candidates:
        name = candidate
        while name.startswith(PACKAGE) and name not in modules:
            name, _, tail = name.rpartition(".")
            if not tail:
                break
        if name in modules:
            found.add(name)
    return found


def roots(modules: set[str]) -> set[str]:
    """Корни графа: всё, откуда пакет зовут в обход импорта из самого пакета."""
    named: list[str] = []
    # Команда `cast`: её ставит `pyproject.toml`, и зовёт её оболочка пользователя.
    named.extend(_entry_points(REPO / "pyproject.toml"))
    # Инструменты и стенды: законные вызывающие продукта наравне с командой. Импорт у них
    # обычный, и увидеть его можно только тем, что `scripts` разобраны как питон.
    for tool in sorted((REPO / "scripts").glob("*.py")):
        named.extend(_imported_by(tool))
    # Установщик зовёт питон строкой (`python -c 'from torrcast...'`), а описания
    # индексеров - данные, которые читает продукт; в обоих случаях имя видно только текстом.
    named.extend(_mentioned_in(REPO / "install.sh"))
    for definition in sorted((REPO / "definitions").glob("*")):
        named.extend(_mentioned_in(definition))
    found = _named(modules, named)
    # `__main__` не импортирует никто по построению: его исполняет `python -m пакет`.
    # Показ так и поднимается отдельным процессом (см. `start_play_unit`), и имя модуля
    # там - строка в команде юнита, до которой графу импортов не дотянуться.
    return found | {module for module in modules if module.rpartition(".")[2] == "__main__"}


def alive_from(graph: grimp.ImportGraph, seeds: set[str]) -> set[str]:
    """Всё, до чего есть путь по импортам от корней."""
    alive = set(seeds)
    queue = list(seeds)
    while queue:
        for imported in graph.find_modules_directly_imported_by(queue.pop()):
            if imported not in alive:
                alive.add(imported)
                queue.append(imported)
    return alive


def orphans(graph: grimp.ImportGraph) -> list[str]:
    """Модули пакета, до которых нет пути ни от одного корня."""
    modules = set(graph.modules)
    # `__init__.py` по правилу «раздача» не раздаёт имён и не импортируется ни у кого:
    # его исполняет питон сам при импорте любого потомка. Пакет - не мертвец, он дом.
    homes = {module for module in modules if graph.find_children(module)}
    dead = modules - alive_from(graph, roots(modules)) - homes
    return [
        f"{module.replace('.', '/')}.py: модуль не импортирует никто" for module in sorted(dead)
    ]


def vulture(*paths: str) -> list[str]:
    """Находки vulture по путям. Код 3 - это находки, всё прочее - поломка стадии."""
    done = subprocess.run(
        [str(REPO / ".venv/bin/vulture"), *paths, WHITELIST],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode not in (0, 3):
        raise SystemExit(f"vulture сорвался, код {done.returncode}:\n{done.stderr}")
    return [line for line in done.stdout.splitlines() if line]


def report(stage: str, found: list[str]) -> int:
    """Напечатать находки стадии и вернуть их число."""
    for line in found:
        print(line)
    print(f"{stage}: {len(found)}")
    return len(found)


def main() -> int:
    """Прогнать три стадии и вернуть ненулевой код, если нашлась хоть одна."""
    found = report("мёртвое в пакете и в инструментах", vulture("torrcast", "scripts"))
    # Отбор строк не смеет подменить собой код возврата: падаем по ЧИСЛУ отобранных
    # находок, а не по коду `grep`. На этом месте проект уже получал ноль на упавшем.
    whole = vulture("torrcast", "tests", "scripts")
    found += report("мёртвое в тестах", [line for line in whole if line.startswith("tests/")])
    found += report("модулей без импортирующих", orphans(grimp.build_graph(PACKAGE)))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
