"""Паспорт прогона: отпечаток кода обязан видеть весь пакет, а не его верхний уровень.

Отпечаток - единственная отметка о коде, которая переживает копирование каталогом: на
стенде ни репозитория, ни git нет, и «тот же ли это код» решается только им. Поэтому
проверяется он отрицательной пробой: правка в подпакете обязана его сдвинуть.

⚠️ Чего эти проверки не обещают: что отпечаток совпадает с коммитом. Он считается по
файлам и про историю не знает ничего - грязное дерево даст свой отпечаток и будет право.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "runpass", Path(__file__).parents[1] / "scripts/runpass.py"
)
assert SPEC and SPEC.loader
runpass = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runpass)


def _package(root: Path, files: dict[str, str]) -> Path:
    """Разложить поддельный пакет: путь от корня - ключ, содержимое - значение."""
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_nested_change_moves_the_fingerprint(tmp_path: Path) -> None:
    """Правка в подпакете двигает отпечаток: иначе паспорт врёт «код тот же»."""
    root = _package(
        tmp_path,
        {
            "torrcast/__init__.py": "",
            "torrcast/domain/pointer_lag.py": "LAG_TICK = 1.0\n",
            "torrcast/adapters/stream_pack/packer_publish.py": "how = 'копия'\n",
        },
    )
    before, count = runpass.fingerprint(root)
    assert count == 3, "в отпечаток обязан войти весь пакет, а не только верхний уровень"
    (root / "torrcast/domain/pointer_lag.py").write_text("LAG_TICK = 2.0\n", encoding="utf-8")
    after, _ = runpass.fingerprint(root)
    assert before != after


def test_same_name_in_two_subpackages_is_not_the_same_file(tmp_path: Path) -> None:
    """Совпадающие имена не схлопываются: в паре стоит путь, а не имя файла."""
    left = _package(
        tmp_path / "left",
        {"torrcast/__init__.py": "", "torrcast/domain/freeze.py": "x = 1\n"},
    )
    right = _package(
        tmp_path / "right",
        {"torrcast/__init__.py": "", "torrcast/adapters/freeze.py": "x = 1\n"},
    )
    assert runpass.fingerprint(left)[0] != runpass.fingerprint(right)[0]


def test_bytecode_cache_is_not_code(tmp_path: Path) -> None:
    """Кэш байт-кода в отпечаток не идёт: он тень кода и живёт своей жизнью."""
    root = _package(tmp_path, {"torrcast/__init__.py": "", "torrcast/domain/grid.py": "x = 1\n"})
    clean, count = runpass.fingerprint(root)
    cache = root / "torrcast/domain/__pycache__"
    cache.mkdir(parents=True)
    (cache / "grid.cpython-311.py").write_text("x = 2\n", encoding="utf-8")
    assert runpass.fingerprint(root) == (clean, count)
