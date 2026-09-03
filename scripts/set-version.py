#!/usr/bin/env python3
"""scripts/set-version.py [X.Y.Z] - разносит номер версии по всему дереву.

Ровно один файл в репозитории хранится руками - `torrcast/domain/version.py`.
Всё, что технически способно прочитать его само, читает само (`pyproject.toml`
через `[tool.hatch.version]`, `cast --version` через прямой импорт модуля).
Всё остальное не умеет читать python на лету (JSON-манифест интеграции для Home
Assistant, `install.sh`, который уезжает отдельным файлом, запись пакета
`torrcast` в `uv.lock`) - эта команда пишет туда номер сама, одной подстановкой
на файл.

Без аргумента номер не меняется - команда только разносит уже записанный в
источнике номер по производным местам (полезно после ручной правки одного из
них или после мержа).

Подстановка идёт ПО ФОРМЕ (`[0-9]+\\.[0-9]+\\.[0-9]+`), а не по литералу
старого значения: файл, отставший на выпуск, обязан найтись и замениться, а не
молча остаться в стороне. Каждая подстановка требует РОВНО ОДНОГО совпадения
в файле - лишнее или нулевое совпадение останавливает команду.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Callable
from pathlib import Path
from re import Match
from typing import NoReturn

ROOT = Path(__file__).resolve().parents[1]
SEMVER = r"[0-9]+\.[0-9]+\.[0-9]+"
VERSION_PY = ROOT / "torrcast" / "domain" / "version.py"
INSTALL_SH = ROOT / "install.sh"
MANIFEST_JSON = ROOT / "custom_components" / "torrcast" / "manifest.json"
UV_LOCK = ROOT / "uv.lock"


def _die(message: str) -> NoReturn:
    raise SystemExit(f"set-version: {message}")


def _substitute_one(path: Path, pattern: str, build: Callable[[Match[str]], str]) -> None:
    """Заменяет РОВНО одно совпадение `pattern` в `path` результатом `build(match)`."""
    if not path.is_file():
        _die(f"{path}: файла нет")
    text = path.read_text(encoding="utf-8")
    matches = list(re.finditer(pattern, text, flags=re.MULTILINE))
    if len(matches) != 1:
        _die(f"{path}: ожидалось ровно одно совпадение формы версии, найдено {len(matches)}")
    match = matches[0]
    replacement = build(match)
    new_text = text[: match.start()] + replacement + text[match.end() :]
    path.write_text(new_text, encoding="utf-8")


def source_version() -> str:
    """Номер, записанный в единственном ручном источнике."""
    if not VERSION_PY.is_file():
        _die(f"{VERSION_PY}: файла нет")
    text = VERSION_PY.read_text(encoding="utf-8")
    found: list[str] = re.findall(rf'^__version__ = "({SEMVER})"$', text, flags=re.MULTILINE)
    if len(found) != 1:
        _die(f"{VERSION_PY}: ожидался ровно один __version__, найдено {len(found)}")
    return found[0]


def set_source_version(version: str) -> None:
    _substitute_one(
        VERSION_PY,
        rf'^__version__ = "{SEMVER}"$',
        lambda m: f'__version__ = "{version}"',
    )


def sync_install_sh(version: str) -> None:
    _substitute_one(
        INSTALL_SH,
        rf"^VERSION='{SEMVER}'$",
        lambda m: f"VERSION='{version}'",
    )


def sync_manifest_json(version: str) -> None:
    def build(match: Match[str]) -> str:
        trailing_comma = "," if match.group(0).rstrip().endswith(",") else ""
        return f'  "version": "{version}"{trailing_comma}'

    _substitute_one(
        MANIFEST_JSON,
        rf'^  "version": "{SEMVER}"(,)?$',
        build,
    )


def sync_uv_lock(version: str) -> None:
    """Правит ТОЛЬКО запись самого пакета `torrcast` - в `uv.lock` версий сотни,
    у каждой зависимости своя, и они не имеют к этой команде отношения."""
    _substitute_one(
        UV_LOCK,
        rf'(?<=^name = "torrcast"\n)version = "{SEMVER}"$',
        lambda m: f'version = "{version}"',
    )


def main(argv: list[str]) -> int:
    args = argv[1:]
    if len(args) > 1:
        _die("лишние аргументы: scripts/set-version.py [X.Y.Z]")
    if args:
        version = args[0]
        if not re.fullmatch(SEMVER, version):
            _die(f"версия не semver: {version!r} (нужен X.Y.Z)")
        set_source_version(version)
    version = source_version()
    sync_install_sh(version)
    sync_manifest_json(version)
    sync_uv_lock(version)
    print(f"версия {version} разнесена: install.sh, manifest.json, uv.lock")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
