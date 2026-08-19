"""Композиционный корень: после сборки след пишет настоящая лента, а не молчание."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal.file_journal import FileJournal
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install, journal
from torrcast.runtime.wire import wire


def test_wiring_puts_the_real_journal_on_the_port() -> None:
    """До сборки след молчит, после - пишет; это и есть работа корня."""
    install(Silent())
    assert isinstance(journal(), Silent)

    wire()

    assert isinstance(journal(), FileJournal)


#: Вопрос задаётся СВЕЖЕМУ процессу и по одному модулю за раз, потому что оба соседа
#: покупают ответ. Общий прогон покупает его чужим импортом: сосед по набору втянул
#: совместимый фасад, и тот раздал среду побочным эффектом. Обход всего дерева в одном
#: процессе покупал его сам у себя: `torrcast/choice.py` импортировался раньше
#: `torrcast/usecases/choice.py` просто по алфавиту - и к моменту вопроса среда уже стояла.
#: Спрашивать надо ровно одно: раздал ли КОРЕНЬ, а не подвернулся ли импорт.
_UNBOUND_AFTER_WIRING = """
import ast, importlib, pathlib, sys

from torrcast.runtime.wire import wire

wire()

name = sys.argv[1]
tree = ast.parse(pathlib.Path(*name.split(".")).with_suffix(".py").read_text(encoding="utf-8"))
declared = [
    node.target.id
    for node in tree.body
    if isinstance(node, ast.AnnAssign) and node.value is None and isinstance(node.target, ast.Name)
]
module = importlib.import_module(name)
for who in declared:
    if not hasattr(module, who):
        print(f"{name}.{who}")
"""


def _modules_with_bare_declarations(root: Path) -> list[str]:
    """Модули, где объявлено имя без значения: «сюда положит корень»."""
    found = []
    for path in sorted((root / "torrcast").rglob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if any(
            isinstance(node, ast.AnnAssign)
            and node.value is None
            and isinstance(node.target, ast.Name)
            for node in tree.body
        ):
            found.append(".".join(path.relative_to(root).with_suffix("").parts))
    return found


@pytest.mark.machine
def test_no_scenario_is_left_without_its_environment() -> None:
    """После сборки не остаётся объявленного, но не связанного имени - у КАЖДОГО модуля.

    Сценариям, которым внешний мир приходит мешком-средой, её раздавал импорт
    совместимого фасада. Фасад прогрева не импортирует никто - и живой каст падал
    ``NameError: _environment`` уже после того, как первые куски уехали на телевизор,
    при том что весь сухой набор был зелёным: в общем прогоне среду успевал раздать
    сосед по набору. Голое объявление без значения - это и есть «сюда положит корень»,
    поэтому мера ровно такая: остались ли такие имена пустыми у собранного приложения.

    ⚠️ Прошлая редакция этой меры спрашивала не то и потому пропустила ровно ту же
    беду у выбора раздачи (TC-630): она делала ``import torrcast.cli`` «как точка входа»,
    а тот тянул фасад, который среду и раздавал. Мера ответа не покупает: корень
    зовётся в одиночку, каждый модуль спрашивается своим процессом.

    Исключений у меры больше нет: последним связыванием вне корня оставался добор
    кандидатов, и оно переехало сюда вместе со сносом фасада ``torrcast.reinforce``.
    """
    root = Path(__file__).resolve().parents[2]
    empty = []
    for name in _modules_with_bare_declarations(root):
        done = subprocess.run(
            [sys.executable, "-c", _UNBOUND_AFTER_WIRING, name],
            capture_output=True,
            text=True,
            check=False,
            cwd=root,
        )
        assert done.returncode == 0, f"{name}: {done.stderr}"
        empty += done.stdout.split()
    assert empty == [], "корень не раздал среду: " + " ".join(empty)
