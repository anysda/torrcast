"""Композиционный корень: после сборки след пишет настоящая лента, а не молчание."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from torrcast.adapters.filesystem.trace_journal import FileJournal
from torrcast.ports.journal import _Silent, install, journal
from torrcast.runtime.wire import wire


def test_wiring_puts_the_real_journal_on_the_port() -> None:
    """До сборки след молчит, после - пишет; это и есть работа корня."""
    install(_Silent())
    assert isinstance(journal(), _Silent)

    wire()

    assert isinstance(journal(), FileJournal)


#: Пересчёт голых объявлений выполняется в СВЕЖЕМ процессе, повторяющем точку входа.
#: В общем прогоне вопрос бессмыслен: любой сосед по набору успел импортировать
#: совместимый фасад, тот раздал среду побочным эффектом - и ответ был бы куплен чужим
#: импортом, а не работой корня.
_UNBOUND_AFTER_WIRING = """
import ast, importlib, pathlib, sys

from torrcast.runtime.wire import wire
import torrcast.cli  # ровно то, что тянет точка входа

wire()

for path in sorted(pathlib.Path(sys.argv[1], "torrcast").rglob("*.py")):
    if path.name == "__init__.py":
        continue
    tree = ast.parse(path.read_text(encoding="utf-8"))
    declared = [
        node.target.id
        for node in tree.body
        if isinstance(node, ast.AnnAssign) and node.value is None
        and isinstance(node.target, ast.Name)
    ]
    if not declared:
        continue
    name = ".".join(path.relative_to(sys.argv[1]).with_suffix("").parts)
    module = importlib.import_module(name)
    for who in declared:
        if not hasattr(module, who):
            print(f"{name}.{who}")
"""


@pytest.mark.machine
def test_no_scenario_is_left_without_its_environment() -> None:
    """После сборки в дереве не остаётся объявленного, но не связанного имени.

    Сценариям, которым внешний мир приходит мешком-средой, её раздавал импорт
    совместимого фасада. Фасад прогрева не импортирует никто - и живой каст падал
    ``NameError: _environment`` уже после того, как первые куски уехали на телевизор,
    при том что весь сухой набор был зелёным: в общем прогоне среду успевал раздать
    сосед по набору. Голое объявление без значения - это и есть «сюда положит корень»,
    поэтому мера ровно такая: остались ли такие имена пустыми у собранного приложения.
    """
    root = Path(__file__).resolve().parents[2]
    done = subprocess.run(
        [sys.executable, "-c", _UNBOUND_AFTER_WIRING, str(root)],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout.split() == [], "корень не раздал среду: " + " ".join(done.stdout.split())
