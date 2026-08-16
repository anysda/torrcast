"""Отрицательные пробы для каждого правила структуры репозитория."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import structure_gate
import symbolmap


def _tree(tmp_path: Path, source: str = '"""Модуль."""\n\nclass Good:\n    pass\n') -> Path:
    (tmp_path / "torrcast").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "torrcast" / "good.py").write_text(source, encoding="utf-8")
    (tmp_path / "tests" / "test_good.py").write_text("", encoding="utf-8")
    (tmp_path / "docs" / "map.md").write_text(symbolmap.render(tmp_path), encoding="utf-8")
    return tmp_path


def _rules(root: Path) -> set[str]:
    return {item.rule for item in structure_gate.check(root)}


def _refresh_map(root: Path) -> None:
    (root / "docs" / "map.md").write_text(symbolmap.render(root), encoding="utf-8")


def test_clean_tree_has_no_violations(tmp_path: Path) -> None:
    assert structure_gate.check(_tree(tmp_path)) == []


def test_length_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, '"""Модуль."""\n' + "# строка\n" * 200)
    _refresh_map(root)
    assert "длина" in _rules(root)


def test_unit_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, '"""Модуль."""\nclass Good: pass\ndef extra(): pass\n')
    _refresh_map(root)
    assert "единица" in _rules(root)


def test_name_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, '"""Модуль."""\nclass WrongName: pass\n')
    _refresh_map(root)
    assert "имя" in _rules(root)


def test_layers_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "usecases").mkdir()
    (root / "tests" / "usecases").mkdir()
    (root / "torrcast" / "usecases" / "run.py").write_text(
        '"""Модуль."""\nimport torrcast.adapters.web\ndef run(): pass\n', encoding="utf-8"
    )
    (root / "tests" / "usecases" / "test_run.py").write_text("", encoding="utf-8")
    _refresh_map(root)
    assert "слои" in _rules(root)


def test_cycles_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "a.py").write_text('"""Модуль А."""\nimport torrcast.b\n', encoding="utf-8")
    (root / "torrcast" / "b.py").write_text('"""Модуль Б."""\nimport torrcast.a\n', encoding="utf-8")
    (root / "tests" / "test_a.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_b.py").write_text("", encoding="utf-8")
    _refresh_map(root)
    assert "циклы" in _rules(root)


def test_docstring_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, "class Good: pass\n")
    _refresh_map(root)
    assert "докстрока" in _rules(root)


def test_mirror_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "tests" / "test_good.py").unlink()
    assert "зеркало" in _rules(root)


def test_mirror_rule_ignores_package_init(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "__init__.py").write_text('"""Пакет."""\n', encoding="utf-8")
    _refresh_map(root)
    assert not any(
        item.rule == "зеркало" and item.path == "torrcast/__init__.py"
        for item in structure_gate.check(root)
    )


def test_io_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "usecases").mkdir()
    (root / "tests" / "usecases").mkdir()
    (root / "torrcast" / "usecases" / "wait.py").write_text(
        '"""Модуль."""\nimport time\ndef wait(): time.sleep(1)\n', encoding="utf-8"
    )
    (root / "tests" / "usecases" / "test_wait.py").write_text("", encoding="utf-8")
    _refresh_map(root)
    assert "ввод-вывод" in _rules(root)


def test_map_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs" / "map.md").write_text("устарела\n", encoding="utf-8")
    assert "карта" in _rules(root)
