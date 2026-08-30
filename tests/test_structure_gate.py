"""Отрицательные пробы для каждого правила структуры репозитория."""

from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "scripts"))

import structure_gate

STRUCTURE_GATE_SCRIPT = Path(__file__).parents[1] / "scripts" / "structure_gate.py"


def _tree(tmp_path: Path, source: str = '"""Модуль."""\n\nclass Good:\n    pass\n') -> Path:
    (tmp_path / "torrcast").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "torrcast" / "good.py").write_text(source, encoding="utf-8")
    (tmp_path / "tests" / "test_good.py").write_text("", encoding="utf-8")
    return tmp_path


def _rules(root: Path) -> set[str]:
    return {item.rule for item in structure_gate.check(root)}


def test_clean_tree_has_no_violations(tmp_path: Path) -> None:
    assert structure_gate.check(_tree(tmp_path)) == []


def test_length_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, '"""Модуль."""\n' + "# строка\n" * 200)
    assert "длина" in _rules(root)


def test_unit_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, '"""Модуль."""\nclass Good: pass\ndef extra(): pass\n')
    assert "единица" in _rules(root)


def test_name_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, '"""Модуль."""\nclass WrongName: pass\n')
    assert "имя" in _rules(root)


def test_layers_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "usecases").mkdir()
    (root / "tests" / "usecases").mkdir()
    (root / "torrcast" / "usecases" / "run.py").write_text(
        '"""Модуль."""\nimport torrcast.adapters.web\ndef run(): pass\n', encoding="utf-8"
    )
    (root / "tests" / "usecases" / "test_run.py").write_text("", encoding="utf-8")
    assert "слои" in _rules(root)


def test_cycles_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "a.py").write_text(
        '"""Модуль А."""\nimport torrcast.b\n', encoding="utf-8"
    )
    (root / "torrcast" / "b.py").write_text(
        '"""Модуль Б."""\nimport torrcast.a\n', encoding="utf-8"
    )
    (root / "tests" / "test_a.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_b.py").write_text("", encoding="utf-8")
    assert "циклы" in _rules(root)


def test_docstring_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path, "class Good: pass\n")
    assert "докстрока" in _rules(root)


def test_mirror_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "tests" / "test_good.py").unlink()
    assert "зеркало" in _rules(root)


def test_mirror_rule_ignores_package_init(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    (root / "torrcast" / "__init__.py").write_text('"""Пакет."""\n', encoding="utf-8")
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
    assert "обход" in _rules(root)


def test_silencer_rule_turns_red_when_the_typechecker_is_switched_off(tmp_path: Path) -> None:
    """Файл, снятый с тайпчека целиком, выглядит проверенным - и не проверен."""
    root = _tree(tmp_path)
    _layered(root, "loose", '"""Модуль."""\n# mypy: ignore-errors\ndef loose(): pass\n')
    assert "глушитель" in _rules(root)


def test_silencer_rule_turns_red_when_undeclared_names_are_hushed(tmp_path: Path) -> None:
    """`F821`/`F822` - единственная проверка на имена из `globals()`; глушить её нельзя."""
    root = _tree(tmp_path)
    _layered(root, "hushed", '"""Модуль."""\n# ruff: noqa: F821, F822\ndef hushed(): pass\n')
    assert "глушитель" in _rules(root)


def _in_layer(root: Path, layer: str, name: str, source: str) -> None:
    """Кладёт модуль в названный слой вместе с его зеркальным тестом."""
    (root / "torrcast" / layer).mkdir(exist_ok=True)
    (root / "tests" / layer).mkdir(exist_ok=True)
    (root / "torrcast" / layer / f"{name}.py").write_text(source, encoding="utf-8")
    (root / "tests" / layer / f"test_{name}.py").write_text("", encoding="utf-8")


def test_trade_rule_turns_red_on_a_slot_typed_any(tmp_path: Path) -> None:
    """Слот композиционного корня, объявленный `Any`, - тот же необъявленный договор."""
    root = _tree(tmp_path)
    _layered(root, "show", '"""Модуль."""\nfrom typing import Any\n\nHlsServer: Any\n')
    assert "размен" in _rules(root)


def test_trade_rule_turns_red_on_a_signature(tmp_path: Path) -> None:
    """Параметр и возврат единицы слоя - договор, и `Any` в них считается тоже."""
    root = _tree(tmp_path)
    _layered(
        root,
        "pack",
        '"""Модуль."""\nfrom typing import Any\n\n\ndef pack(grid: Any) -> Any:\n    return grid\n',
    )
    assert len([item for item in structure_gate.check(root) if item.rule == "размен"]) == 2


def test_trade_rule_turns_red_on_a_type_alias_in_a_port(tmp_path: Path) -> None:
    """У порта договор и есть всё содержимое: `RawRow: TypeAlias = Any` не называет ничего."""
    root = _tree(tmp_path)
    _in_layer(
        root,
        "ports",
        "raw_row",
        '"""Модуль."""\nfrom typing import Any, TypeAlias\n\nRawRow: TypeAlias = Any\n',
    )
    assert "размен" in _rules(root)


def test_trade_rule_counts_any_hidden_inside_a_generic(tmp_path: Path) -> None:
    """`Callable[..., Any]` разменивает договор ровно так же, как голое `Any`."""
    root = _tree(tmp_path)
    _layered(
        root,
        "grid",
        '"""Модуль."""\nfrom collections.abc import Callable\nfrom typing import Any\n\n'
        "grid_for: Callable[..., Any]\n",
    )
    assert "размен" in _rules(root)


def test_trade_rule_reads_through_quotes(tmp_path: Path) -> None:
    """Кавычки правило не покупают: строковая аннотация разбирается тем же разбором."""
    root = _tree(tmp_path)
    _layered(root, "quoted", '"""Модуль."""\n\n\ndef quoted() -> "Any":\n    return 1\n')
    assert "размен" in _rules(root)


def test_trade_rule_looks_inside_a_type_checking_block(tmp_path: Path) -> None:
    """Объявление под `if TYPE_CHECKING:` тайпчек читает наравне с голым - значит и мы."""
    root = _tree(tmp_path)
    _layered(
        root,
        "planned",
        '"""Модуль."""\nfrom typing import TYPE_CHECKING, Any, TypeAlias\n\n'
        "if TYPE_CHECKING:\n    Plan: TypeAlias = Any\n",
    )
    assert "размен" in _rules(root)


def test_trade_rule_reads_any_under_a_borrowed_name(tmp_path: Path) -> None:
    """Имя `Any` в файле любое: `from typing import Any as A` не покупает меру."""
    root = _tree(tmp_path)
    _layered(root, "show", '"""Модуль."""\nfrom typing import Any as A\n\nHlsServer: A\n')
    traded = [item for item in structure_gate.check(root) if item.rule == "размен"]
    assert [(item.line, item.message) for item in traded] == [
        (4, "тип слота не назван: HlsServer: A")
    ]


def test_trade_rule_follows_a_chain_of_aliases(tmp_path: Path) -> None:
    """Псевдоним псевдонима - тот же `Any`: цепочка `A` -> `B` разбирается до дна.

    Подпись зовёт оба имени намеренно: список имён не должен зависеть от того, что мера
    успела встретить раньше по файлу. Одно только `grid: B` проглядело бы подмену списка
    именами очередного присваивания.
    """
    root = _tree(tmp_path)
    _layered(
        root,
        "pack",
        '"""Модуль."""\nfrom typing import Any as A\n\nB = A\n\n\n'
        "def pack(grid: B, raw: A) -> int:\n    return len(grid) + len(raw)\n",
    )
    traded = [item for item in structure_gate.check(root) if item.rule == "размен"]
    assert [item.message for item in traded] == [
        "имя подменено на Any: B",
        "тип параметра не назван: pack(grid)",
        "тип параметра не назван: pack(raw)",
    ]


def test_trade_rule_reads_any_by_its_full_name(tmp_path: Path) -> None:
    """`import typing as t` с `t.Any` - тот же размен: имя ловится по последней части."""
    root = _tree(tmp_path)
    _layered(root, "probe", '"""Модуль."""\nimport typing as t\n\nreply: t.Any\n')
    assert "размен" in _rules(root)


def test_trade_rule_reads_a_renamed_type_alias(tmp_path: Path) -> None:
    """Переименованный `TypeAlias` тоже не покупает меру: договор лежит в значении."""
    root = _tree(tmp_path)
    _in_layer(
        root,
        "ports",
        "raw_row",
        '"""Модуль."""\nfrom typing import Any, TypeAlias as TA\n\nRawRow: TA = Any\n',
    )
    assert "размен" in _rules(root)


def test_trade_rule_leaves_a_borrowed_name_in_the_adapter_alone(tmp_path: Path) -> None:
    """Исключение слоя адаптеров намеренное: под чужим именем оно остаётся тем же."""
    root = _tree(tmp_path)
    _in_layer(
        root,
        "adapters",
        "probe",
        '"""Модуль."""\nfrom typing import Any as A\n\nB = A\n\nreply: B\n',
    )
    assert "размен" not in _rules(root)


def test_trade_rule_leaves_the_adapter_boundary_alone(tmp_path: Path) -> None:
    """Законный `Any` вынесен целым слоем: на границе с чужой библиотекой типов у нас нет."""
    root = _tree(tmp_path)
    _in_layer(
        root,
        "adapters",
        "probe",
        '"""Модуль."""\nfrom typing import Any\n\n\ndef probe(reply: Any) -> Any:\n'
        "    return reply\n",
    )
    assert "размен" not in _rules(root)


def test_trade_rule_leaves_a_local_variable_alone(tmp_path: Path) -> None:
    """Правило считает договор, а не тела: `Any` у локальной переменной - дело одного места."""
    root = _tree(tmp_path)
    _layered(
        root,
        "local",
        '"""Модуль."""\nfrom typing import Any\n\n\ndef local() -> int:\n'
        "    seen: dict[str, Any] = {}\n    return len(seen)\n",
    )
    assert "размен" not in _rules(root)


def test_trade_rule_leaves_a_reexported_name_alone(tmp_path: Path) -> None:
    """`"Any"` в `__all__` называет реэкспорт имени, а не размен договора."""
    root = _tree(tmp_path)
    _layered(root, "facade", '"""Модуль."""\n\n__all__ = ["Any"]\n')
    assert "размен" not in _rules(root)


def test_silencer_rule_leaves_a_narrow_exception_alone(tmp_path: Path) -> None:
    """Точечное исключение по делу - не глушитель: правило бьёт по выключению ЦЕЛИКОМ.

    Иначе правило запретило бы всякое подавление и его начали бы обходить обратно - уже
    построчными `# noqa`, которые гейт не видит вовсе.
    """
    root = _tree(tmp_path)
    _layered(root, "narrow", '"""Модуль."""\n# ruff: noqa: RUF001\ndef narrow(): pass\n')
    assert "глушитель" not in _rules(root)


def _package(root: Path, name: str, init: str, module: str = "digest") -> None:
    """Кладёт пакет с подмодулем и его зеркальным тестом."""
    (root / "torrcast" / name).mkdir(exist_ok=True)
    (root / "tests" / name).mkdir(exist_ok=True)
    (root / "torrcast" / name / "__init__.py").write_text(init, encoding="utf-8")
    (root / "torrcast" / name / f"{module}.py").write_text(
        f'"""Модуль."""\n\n\ndef {module}(): pass\n', encoding="utf-8"
    )
    (root / "tests" / name / f"test_{module}.py").write_text("", encoding="utf-8")


def test_handout_rule_turns_red_on_a_name_from_a_submodule(tmp_path: Path) -> None:
    """Одна строка возвращает имени второй адрес - витрину пакета вместо дома."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nfrom .digest import digest\n')
    handed = [item for item in structure_gate.check(root) if item.rule == "раздача"]
    assert [item.message for item in handed] == [
        "пакет раздаёт имя digest из torrcast.notes.digest"
    ]


def test_handout_rule_turns_red_on_a_name_taken_by_its_full_address(tmp_path: Path) -> None:
    """Полный путь раздаёт имя ровно так же, как точка: считается запись, а не длина."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nfrom torrcast.notes.digest import digest\n')
    assert "раздача" in _rules(root)


def test_handout_rule_turns_red_on_a_submodule_shadowed_by_its_own_init(tmp_path: Path) -> None:
    """Затенённый подмодуль домом не является: `digest` в пакете - функция, а не модуль."""
    root = _tree(tmp_path)
    _package(root, "digest", '"""Пакет."""\n\nfrom torrcast.digest.digest import digest\n')
    assert "раздача" in _rules(root)


def test_handout_rule_turns_red_on_a_renamed_import(tmp_path: Path) -> None:
    """Псевдоним заводит модулю второй адрес - иначе правило покупается словом `as`."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nimport torrcast.notes.digest as short\n')
    assert "раздача" in _rules(root)


def test_handout_rule_turns_red_on_a_renamed_home(tmp_path: Path) -> None:
    """`from . import digest as short` называет дом чужим именем - это второй адрес."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nfrom . import digest as short\n')
    assert "раздача" in _rules(root)


def test_handout_rule_turns_red_on_a_wholesale_reexport(tmp_path: Path) -> None:
    """`import *` раздаёт весь подмодуль сразу, не называя ни одного имени."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nfrom .digest import *\n')
    assert "раздача" in _rules(root)


def test_handout_rule_turns_red_on_a_borrowed_name(tmp_path: Path) -> None:
    """Чужое имя раздаётся наравне со своим: `Path` в namespace пакета берут оттуда."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nfrom pathlib import Path\n')
    assert "раздача" in _rules(root)


def test_handout_rule_leaves_naming_a_home_alone(tmp_path: Path) -> None:
    """`import подмодуль` и `from . import подмодуль` называют дом, второго адреса нет.

    Без этой пробы правило запретило бы пакету называть собственные дома - и его сняли бы
    целиком вместе с проверкой на раздачу имён.
    """
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n\nimport torrcast.notes.digest\nfrom . import digest\n')
    assert "раздача" not in _rules(root)


def test_handout_rule_leaves_an_ordinary_module_alone(tmp_path: Path) -> None:
    """Правило про namespace пакета: обычный модуль зовёт соседа как звал."""
    root = _tree(tmp_path)
    _package(root, "notes", '"""Пакет."""\n')
    (root / "torrcast" / "notes" / "reader.py").write_text(
        '"""Модуль."""\n\nfrom .digest import digest\n\n\ndef reader(): return digest\n',
        encoding="utf-8",
    )
    (root / "tests" / "notes" / "test_reader.py").write_text("", encoding="utf-8")
    assert "раздача" not in _rules(root)


def test_environment_rule_turns_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    _layered(root, "handle", '"""Модуль."""\nimport os\nHANDLE = os.environ.get("TORRCAST_X")\n')
    assert "окружение" in _rules(root)


def test_environment_rule_reads_a_handle_taken_by_a_borrowed_name(tmp_path: Path) -> None:
    """Ручка берётся по смыслу, а не по букве: `from os import environ, getenv`."""
    root = _tree(tmp_path)
    _layered(
        root,
        "borrowed",
        '"""Модуль."""\nfrom os import environ, getenv\n'
        'A = environ["TORRCAST_X"]\nB = getenv("TORRCAST_Y")\n',
    )
    assert len([item for item in structure_gate.check(root) if item.rule == "окружение"]) == 2


def test_environment_rule_leaves_a_handle_asked_at_the_call_alone(tmp_path: Path) -> None:
    """Ручка, спрошенная в момент вызова, - это довод, а не застывшее на импорте значение."""
    root = _tree(tmp_path)
    _layered(
        root,
        "asked",
        '"""Модуль."""\nimport os\ndef asked() -> str:\n'
        '    return os.environ.get("TORRCAST_X", "")\n',
    )
    assert "окружение" not in _rules(root)


def _shim_tree(tmp_path: Path, source: str) -> Path:
    """Дерево, где по названной границе (:data:`structure_gate.SCRIPTS`) лежит скрипт."""
    root = _tree(tmp_path)
    (root / "scripts").mkdir()
    (root / next(iter(structure_gate.SCRIPTS))).write_text(source, encoding="utf-8")
    return root


def test_the_named_script_is_measured_by_the_gate(tmp_path: Path) -> None:
    """🔴 TC-684. Обход DPI живёт скриптом, и границу эту гейт знает поимённо.

    Пока скрипт лежал вне мерки, ни одно правило раскладки на него не распространялось,
    хотя поднимается он службой и часть каталога достижима только через него.
    """
    root = _shim_tree(tmp_path, 'import os\n\nHANDLE = os.environ.get("TORRCAST_X")\n')
    assert {"докстрока", "зеркало", "окружение"} <= _rules(root)


def test_the_named_script_may_not_grow_past_its_named_debt(tmp_path: Path) -> None:
    """Долг скрипта назван числом: он не порог, и вырасти ему нельзя."""
    debt = next(iter(structure_gate.SCRIPTS.values()))
    root = _shim_tree(tmp_path, '"""Обход."""\n' + "# строка\n" * debt.lines)
    (root / debt.mirror).write_text("", encoding="utf-8")
    assert "длина" in _rules(root)
    assert "зеркало" not in _rules(root), "зеркало у скрипта названо поимённо"


def _mirror(root: Path, body: str) -> Path:
    """Написать зеркалу модуля `good` тело теста и вернуть корень."""
    (root / "tests" / "test_good.py").write_text(
        f'"""Зеркало."""\n\nfrom torrcast.good import Good\n\n\ndef test_good() -> None:\n{body}',
        encoding="utf-8",
    )
    return root


def test_check_rule_turns_red_on_a_test_that_holds_only_the_import(tmp_path: Path) -> None:
    """Файл зеркала есть, счётчик `зеркало` нулевой, а проверки в файле нет."""
    root = _mirror(_tree(tmp_path), "    assert Good is not None\n")
    assert "проверка" in _rules(root)


def test_check_rule_leaves_a_test_that_calls_the_unit_alone(tmp_path: Path) -> None:
    """То же утверждение о том, что тест ПОСЧИТАЛ, - это уже поведение."""
    root = _mirror(_tree(tmp_path), "    assert Good() is not None\n")
    assert "проверка" not in _rules(root)


def test_check_rule_leaves_a_name_the_test_made_itself_alone(tmp_path: Path) -> None:
    """Имя, заведённое внутри теста, держит результат, а не импорт."""
    root = _mirror(_tree(tmp_path), "    found = Good()\n    assert found is not None\n")
    assert "проверка" not in _rules(root)


def test_check_rule_counts_the_whole_test_and_not_a_single_line(tmp_path: Path) -> None:
    """Пустая строка рядом с настоящей проверкой - лишняя строка, а не купленная зелень."""
    root = _mirror(_tree(tmp_path), "    assert Good is not None\n    assert Good().ok\n")
    assert "проверка" not in _rules(root)


def test_check_rule_leaves_a_test_without_a_single_assert_alone(tmp_path: Path) -> None:
    """Предмет правила - утверждение про импорт; тест «не падает» держат другие меры."""
    root = _mirror(_tree(tmp_path), "    Good()\n")
    assert "проверка" not in _rules(root)


def _said(tmp_path: Path, body: str) -> Path:
    """Дерево с одной функцией, которая что-то говорит человеку."""
    return _tree(tmp_path, '"""Модуль."""\n\n\ndef good() -> str:\n    """Единица."""\n' + body)


def test_translation_rule_sees_a_caption_glued_by_an_f_string(tmp_path: Path) -> None:
    """🔴 Ровно то, мимо чего старое правило проходило: надпись собрана f-строкой.

    Живой образец со стенда - `cast --tv` печатал «ТВ: {имя} - {адрес}» и «ищу приёмники
    в сети», и голого литерала в `print` там не было ни одного.
    """
    root = _said(tmp_path, '    name = "гостиная"\n    print(f"ТВ: {name}")\n    return name\n')
    assert "перевод" in _rules(root)


def test_translation_rule_sees_a_caption_that_came_through_a_name(tmp_path: Path) -> None:
    """Надпись положили в переменную, а сказали переменную - это та же надпись."""
    root = _said(tmp_path, '    said = "приёмников не нашёл"\n    return said\n')
    assert "перевод" in _rules(root)


def test_translation_rule_sees_a_caption_built_from_name_into_name(tmp_path: Path) -> None:
    """Цепочка имён длиннее одного шага правило не обманывает."""
    body = '    head = "беру"\n    whole = f"{head} картину"\n    print(whole)\n    return whole\n'
    assert "перевод" in _rules(_said(tmp_path, body))


def test_translation_rule_sees_a_caption_carried_by_an_error(tmp_path: Path) -> None:
    """Отказ человек читает так же, как обычную строку."""
    root = _said(tmp_path, '    raise ValueError("картины не нашлось")\n')
    assert "перевод" in _rules(root)


def test_translation_rule_sees_a_caption_handed_to_a_port_of_show(tmp_path: Path) -> None:
    """Имена методов взяты из портов показа, а не из списка «где обычно печатают»."""
    root = _said(tmp_path, '    self.console.write("готово")\n    return ""\n')
    assert "перевод" in _rules(root)


def test_translation_rule_leaves_a_docstring_alone(tmp_path: Path) -> None:
    """Докстроки остаются русскими решением проекта - надписью они не считаются."""
    root = _said(tmp_path, '    return "ok"\n')
    assert "перевод" not in _rules(root)


def test_translation_rule_leaves_an_inner_tag_of_another_unit_alone(tmp_path: Path) -> None:
    """Метка правила, уехавшая в чужой конструктор, человеку не показывается.

    ``Take(why="номер флагом")`` - внутренняя запись о том, каким правилом взята картина.
    Считай правило и её надписью - оно требовало бы перевести то, чего никто не читает.
    """
    root = _said(tmp_path, '    return Take(1, why="номер флагом")\n')
    assert "перевод" not in _rules(root)


def test_translation_rule_leaves_a_latin_caption_alone(tmp_path: Path) -> None:
    """Правило ловит кириллицу: английская надпись уже прошла каталог или им и рождена."""
    root = _said(tmp_path, '    print("taking the liveliest")\n    return ""\n')
    assert "перевод" not in _rules(root)


def _one_module(tmp_path: Path, relative: str, source: str) -> structure_gate.Module:
    path = tmp_path / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")
    return structure_gate.Module(
        path=path,
        relative=relative,
        name=relative[:-3].replace("/", "."),
        layer=relative.split("/")[1] if relative.count("/") > 1 else "domain",
        tree=ast.parse(source),
        lines=len(source.splitlines()),
    )


def test_translation_rule_counts_two_different_captions_on_one_line(tmp_path: Path) -> None:
    """🔴 Дыра TC-929/3: тернарник кладёт две РАЗНЫЕ надписи на одну строку.

    Схлопывание по номеру строки годилось для частей одной f-строки (``раздача {base}
    - ни серта`` даёт две константы на одну надпись), но тем же ключом ловило и вторую,
    вовсе не связанную надпись, которой выпало жить на той же строке (тернарник,
    ``or``-запасной вариант) - она пропадала с гейта молча, а охват не двигался.
    """
    source = (
        '"""Модуль."""\n\n\n'
        "def codec_name(codec: str, depth: int) -> str:\n"
        '    """Единица."""\n'
        '    return f"{codec} {depth} бит" if depth > 8 else f"{codec} без глубины"\n'
    )
    module = _one_module(tmp_path, "torrcast/good.py", source)
    assert len(structure_gate._spoken_places(module)) == 2


def test_translation_rule_still_collapses_one_f_string_to_one_caption(tmp_path: Path) -> None:
    """Части ОДНОЙ f-строки по-прежнему одна надпись - это не пробой, а сама мера.

    ``раздача {base} - ни серта`` даёт две константы (текст до и после ``{base}``) на
    одну надпись человеку - их и раньше, и теперь положено считать за одно место.
    """
    source = (
        '"""Модуль."""\n\n\n'
        "def good(base: str) -> str:\n"
        '    """Единица."""\n'
        '    return f"раздача {base} - ни серта"\n'
    )
    module = _one_module(tmp_path, "torrcast/good.py", source)
    assert len(structure_gate._spoken_places(module)) == 1


def test_translation_debt_may_not_grow(tmp_path: Path) -> None:
    """Мест стало больше записанного - надпись написали в обход каталога."""
    source = '"""Модуль."""\n\n\ndef good() -> str:\n    """Единица."""\n    return "беру"\n'
    module = _one_module(tmp_path, "torrcast/good.py", source)
    structure_gate.TRANSLATION_DEBT["torrcast/good.py"] = 0
    try:
        messages = [item.message for item in structure_gate._translation_violations(module)]
    finally:
        del structure_gate.TRANSLATION_DEBT["torrcast/good.py"]
    assert messages == ["долг вырос: мест 1, записано 0"]


def test_translation_debt_may_not_go_stale(tmp_path: Path) -> None:
    """Мест стало меньше записанного - запись протухла и прячет место под собой.

    🔴 Долг, записанный с запасом, - это выключенное правило: в файл можно дописать
    надпись, и число не шелохнётся. Поэтому число сверяется точно, а не «не больше».
    """
    source = '"""Модуль."""\n\n\ndef good() -> str:\n    """Единица."""\n    return "ok"\n'
    module = _one_module(tmp_path, "torrcast/good.py", source)
    structure_gate.TRANSLATION_DEBT["torrcast/good.py"] = 3
    try:
        messages = [item.message for item in structure_gate._translation_violations(module)]
    finally:
        del structure_gate.TRANSLATION_DEBT["torrcast/good.py"]
    assert messages == ["долг записан 3, а мест 0 - запись протухла, поправь число"]


def test_translation_debt_named_on_a_file_that_is_gone_turns_red(tmp_path: Path) -> None:
    """Файл переименовали - запись о нём осталась висеть и мерить перестала."""
    module = _one_module(tmp_path, "torrcast/good.py", '"""Модуль."""\n')
    structure_gate.TRANSLATION_DEBT["torrcast/vanished.py"] = 1
    try:
        found = structure_gate._translation_list_violations([module])
    finally:
        del structure_gate.TRANSLATION_DEBT["torrcast/vanished.py"]
    assert ("torrcast/vanished.py", "долг записан на файл, которого нет") in [
        (item.path, item.message) for item in found
    ]


def test_a_permanent_exclusion_without_a_single_live_place_turns_red(tmp_path: Path) -> None:
    """Вечное исключение без единого живого места - место, где можно спрятать надпись."""
    module = _one_module(tmp_path, "torrcast/good.py", '"""Модуль."""\n')
    found = structure_gate._translation_list_violations([module])
    stale = {item.path for item in found if item.message == "исключение без единого живого места"}
    assert stale == set(structure_gate.TRANSLATION_SUBJECT)


def test_the_lists_are_not_measured_against_a_foreign_tree(tmp_path: Path) -> None:
    """Списки описывают дерево гейта; синтетический корень они не описывают вовсе."""
    assert structure_gate._owns_the_lists(Path(structure_gate.__file__).parents[1])
    assert not structure_gate._owns_the_lists(_tree(tmp_path))


def test_a_zero_proven_on_an_empty_set_turns_red(tmp_path: Path) -> None:
    """Правило, не нашедшее ни одного места, объявляет себя ослепшим, а не чистым.

    🔴 Ноль на пустом множестве неотличим от нуля на чистом дереве: сломай разбор -
    и «нарушений нет» будет означать «мерить перестало». Поэтому охват сверяется сам.
    """
    module = _one_module(tmp_path, "torrcast/good.py", '"""Модуль."""\n')
    messages = [item.message for item in structure_gate._translation_list_violations([module])]
    assert any(item.startswith("под мерой файлов 1, а мест не найдено") for item in messages)


def test_the_rule_proves_its_zero_on_the_whole_live_tree() -> None:
    """Охват правила равен дереву на диске, а не тому, до чего оно случайно дошло.

    Числа берутся с двух сторон: файлы считаются прямо на диске, места - разбором.
    Совпали - значит зелень правила стоит на 975 файлах и 597 найденных местах, а не
    на пустоте.
    """
    root = Path(structure_gate.__file__).parents[1]
    modules = structure_gate._load_modules(root)
    measured, seen, places = structure_gate.translation_volume(modules)
    on_disk = [
        path.relative_to(root).as_posix()
        for folder in ("torrcast", "tgbot")
        for path in (root / folder).rglob("*.py")
    ]
    on_disk += [name for name in structure_gate.SCRIPTS if (root / name).exists()]
    assert measured == len([name for name in on_disk if not structure_gate._under_subject(name)])
    # Долг - поимённая опись найденного, и сумма описи обязана сойтись с разбором:
    # разойдётся - либо правило ослепло, либо число в описи написано от руки.
    assert seen == len(structure_gate.TRANSLATION_DEBT)
    assert places == sum(structure_gate.TRANSLATION_DEBT.values())


def test_the_sample_cluster_is_clean_on_a_counted_number_of_files() -> None:
    """Ноль образца назван числом файлов: пустой список тоже даёт ноль нарушений."""
    root = Path(structure_gate.__file__).parents[1]
    modules = structure_gate._load_modules(root)
    sample = [item for item in modules if item.relative.startswith("torrcast/usecases/choice/")]
    assert len(sample) == len(list((root / "torrcast" / "usecases" / "choice").rglob("*.py")))
    assert len(sample) > 1
    assert [item.relative for item in sample if structure_gate._spoken_places(item)] == []


def _git_tree(tmp_path: Path, names: tuple[str, ...]) -> Path:
    """Настоящий git-репозиторий с отслеженными файлами - мера правила это `git ls-files`,
    и синтетическим каталогом без `.git` её не проверить."""
    for name in names:
        (tmp_path / name).write_text("", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    if names:
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    return tmp_path


@pytest.mark.machine
def test_document_rule_allows_readme_alone(tmp_path: Path) -> None:
    root = _git_tree(tmp_path, ("README.md",))
    assert structure_gate._document_violations(root) == []


@pytest.mark.machine
def test_document_rule_allows_readme_and_its_russian_twin(tmp_path: Path) -> None:
    root = _git_tree(tmp_path, ("README.md", "README-ru.md"))
    assert structure_gate._document_violations(root) == []


@pytest.mark.machine
def test_document_rule_turns_red_on_a_third_markdown_that_looks_legitimate(
    tmp_path: Path,
) -> None:
    """`README-en.md` ловит подмену точного списка маской - `docs/notes.md` бы не поймал."""
    root = _git_tree(tmp_path, ("README.md", "README-en.md"))
    violations = structure_gate._document_violations(root)
    assert [item.path for item in violations] == ["README-en.md"]
    assert {item.rule for item in violations} == {"документы"}


@pytest.mark.machine
def test_document_rule_turns_red_when_git_ls_files_sees_nothing(tmp_path: Path) -> None:
    """Пустой ответ `git ls-files` - сломанный замер, а не чистое дерево."""
    root = _git_tree(tmp_path, ())
    violations = structure_gate._document_violations(root)
    assert len(violations) == 1
    assert violations[0].rule == "документы"
    assert "ослеп" in violations[0].message


@pytest.mark.machine
def test_document_rule_is_wired_into_the_entry_point(tmp_path: Path) -> None:
    """Сторож проводки: доказывает не то, что правило умеет краснеть, а то, что его
    в принципе спрашивают из точки входа - гоняет модуль отдельным процессом, как его
    зовёт `scripts/structure-gate`, а не импортом одной функции."""
    root = _git_tree(tmp_path, ("README.md", "README-en.md"))
    completed = subprocess.run(
        [sys.executable, str(STRUCTURE_GATE_SCRIPT), str(root), "--strict"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "README-en.md" in completed.stdout
