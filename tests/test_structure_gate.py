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


def _layered(root: Path, name: str, source: str) -> None:
    """Кладёт модуль в слой сценариев вместе с его зеркальным тестом."""
    (root / "torrcast" / "usecases").mkdir(exist_ok=True)
    (root / "tests" / "usecases").mkdir(exist_ok=True)
    (root / "torrcast" / "usecases" / f"{name}.py").write_text(source, encoding="utf-8")
    (root / "tests" / "usecases" / f"test_{name}.py").write_text("", encoding="utf-8")


def test_bypass_rule_turns_red_on_a_dependency_named_by_a_string(tmp_path: Path) -> None:
    """Правило `обход` своей отрицательной пробы не имело - вот она."""
    root = _tree(tmp_path)
    _layered(
        root,
        "pull",
        '"""Модуль."""\nfrom importlib import import_module\n'
        "def pull(): return import_module('torrcast.good')\n",
    )
    _refresh_map(root)
    assert "обход" in _rules(root)


def test_bypass_rule_turns_red_on_a_stub_beside_a_package_init(tmp_path: Path) -> None:
    """Заглушка рядом с `__init__.py` - такая же ложь компилятору, как и рядом с модулем."""
    root = _tree(tmp_path)
    (root / "torrcast" / "usecases").mkdir()
    (root / "tests" / "usecases").mkdir()
    (root / "torrcast" / "usecases" / "__init__.py").write_text('"""Пакет."""\n', encoding="utf-8")
    (root / "torrcast" / "usecases" / "__init__.pyi").write_text(
        "from torrcast.good import Good as Good\n", encoding="utf-8"
    )
    _refresh_map(root)
    assert "обход" in _rules(root)


def test_silencer_rule_turns_red_when_the_typechecker_is_switched_off(tmp_path: Path) -> None:
    """Файл, снятый с тайпчека целиком, выглядит проверенным - и не проверен."""
    root = _tree(tmp_path)
    _layered(root, "loose", '"""Модуль."""\n# mypy: ignore-errors\ndef loose(): pass\n')
    _refresh_map(root)
    assert "глушитель" in _rules(root)


def test_silencer_rule_turns_red_when_undeclared_names_are_hushed(tmp_path: Path) -> None:
    """`F821`/`F822` - единственная проверка на имена из `globals()`; глушить её нельзя."""
    root = _tree(tmp_path)
    _layered(root, "hushed", '"""Модуль."""\n# ruff: noqa: F821, F822\ndef hushed(): pass\n')
    _refresh_map(root)
    assert "глушитель" in _rules(root)


def test_silencer_rule_leaves_a_narrow_exception_alone(tmp_path: Path) -> None:
    """Точечное исключение по делу - не глушитель: правило бьёт по выключению ЦЕЛИКОМ.

    Иначе правило запретило бы всякое подавление и его начали бы обходить обратно - уже
    построчными `# noqa`, которые гейт не видит вовсе.
    """
    root = _tree(tmp_path)
    _layered(root, "narrow", '"""Модуль."""\n# ruff: noqa: RUF001\ndef narrow(): pass\n')
    _refresh_map(root)
    assert "глушитель" not in _rules(root)


def test_map_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "docs" / "map.md").write_text("устарела\n", encoding="utf-8")
    assert "карта" in _rules(root)
