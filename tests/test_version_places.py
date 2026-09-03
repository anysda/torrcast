"""Ограждение: один ручной источник номера версии, всё прочее с ним согласовано.

`torrcast/domain/version.py` - единственное место, которое человек правит руками.
`pyproject.toml` читает его сам (hatchling, `[tool.hatch.version]`). Всё, что не умеет
читать python на лету - JSON-манифест интеграции для Home Assistant, `install.sh`,
запись пакета `torrcast` в `uv.lock`, эталон `cli-contract` про `--version` - обязано
совпасть с источником; расхождение чинится `scripts/set-version.py`, не тестом.

Каждое место - отдельный тест: порча одного не тонет в общем ответе, а падает своим
именем.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).parents[1]
SEMVER = r"[0-9]+\.[0-9]+\.[0-9]+"
VERSION_PY = REPO / "torrcast" / "domain" / "version.py"
INSTALL_SH = REPO / "install.sh"
MANIFEST_JSON = REPO / "custom_components" / "torrcast" / "manifest.json"
UV_LOCK = REPO / "uv.lock"
PYPROJECT = REPO / "pyproject.toml"


def source_version() -> str:
    text = VERSION_PY.read_text(encoding="utf-8")
    found: list[str] = re.findall(rf'^__version__ = "({SEMVER})"$', text, flags=re.MULTILINE)
    assert len(found) == 1, f"{VERSION_PY}: ожидался ровно один __version__, найдено {len(found)}"
    return found[0]


def test_pyproject_toml_has_no_version_literal_and_reads_the_source() -> None:
    """Требование продукта: `pyproject.toml` литерала номера больше не содержит."""
    text = PYPROJECT.read_text(encoding="utf-8")
    assert not re.search(rf'^version = "{SEMVER}"$', text, flags=re.MULTILINE), (
        "pyproject.toml снова хранит литерал версии - это восьмое ручное место"
    )
    assert 'dynamic = ["version"]' in text
    assert re.search(r'\[tool\.hatch\.version\]\s*\npath = "torrcast/domain/version\.py"', text), (
        "pyproject.toml не указывает hatchling, откуда брать версию"
    )


def test_install_sh_version_matches_the_source() -> None:
    text = INSTALL_SH.read_text(encoding="utf-8")
    found = re.findall(rf"^VERSION='({SEMVER})'$", text, flags=re.MULTILINE)
    assert len(found) == 1, f"install.sh: ожидалась одна строка VERSION=, найдено {len(found)}"
    assert found[0] == source_version()


def test_manifest_json_version_matches_the_source() -> None:
    text = MANIFEST_JSON.read_text(encoding="utf-8")
    found = re.findall(rf'^  "version": "({SEMVER})",?$', text, flags=re.MULTILINE)
    assert len(found) == 1, f"manifest.json: ожидалась одна версия, найдено {len(found)}"
    assert found[0] == source_version()


def test_uv_lock_torrcast_entry_matches_the_source() -> None:
    """Правит и сверяет ТОЛЬКО запись самого `torrcast` - в `uv.lock` версий сотни,
    у каждой зависимости своя."""
    text = UV_LOCK.read_text(encoding="utf-8")
    found = re.findall(rf'^name = "torrcast"\nversion = "({SEMVER})"$', text, flags=re.MULTILINE)
    assert len(found) == 1, f"uv.lock: запись пакета torrcast не найдена одна, найдено {len(found)}"
    assert found[0] == source_version()


def test_cli_contract_version_fixtures_hold_a_template_not_a_literal() -> None:
    """`version.out` подставляет номер из дерева, а не хранит его - см. `scripts/cli-
    contract`. Тот же приём, которым чинили константу в `tests/test_installupgrade.py`."""
    for tongue in ("en", "ru"):
        path = REPO / "tests" / "fixtures" / "cli-contract" / tongue / "version.out"
        text = path.read_text(encoding="utf-8")
        assert text == "torrcast {VERSION}\n", (
            f"{path}: эталон обязан быть шаблоном `torrcast {{VERSION}}`, не номером"
        )


# Единственные места, которым разрешено содержать форму номера версии в идиомах ниже.
# Новое место в этом списке не появляется само - тест его туда не пустит.
KNOWN_VERSION_LOCATIONS = {
    VERSION_PY,
    INSTALL_SH,
    MANIFEST_JSON,
}

_PY_MARKER = re.compile(rf'^__version__ = "{SEMVER}"$')
_SHELL_MARKER = re.compile(rf"^VERSION='{SEMVER}'$")
_CLI_MARKER = re.compile(rf"^torrcast {SEMVER}$")
_JSON_MARKER = re.compile(rf'^  "version": "{SEMVER}",?$')


@pytest.mark.machine
def test_no_new_place_hardcodes_the_version_outside_the_known_list() -> None:
    """Сторож рождения восьмого места.

    Ищет по всему отслеженному дереву три узких, различимых идиомы этого проекта:
    `__version__ = "X.Y.Z"` (source), `VERSION='X.Y.Z'` (install.sh) и печатаемый банер
    `torrcast X.Y.Z` (CLI-эталон - но он теперь шаблон, живых совпадений тут не бывает).
    Совпадение обязано лежать в уже известном месте, иначе это - новое ручное место,
    которое молча разойдётся с источником при следующем подъёме версии.

    JSON-форма (`"version": "X.Y.Z"`) сканируется только у файлов `manifest.json` -
    ключ `version` в JSON слишком общий (см. `tests/hass_integration/fixtures/state-
    playing.json`, где то же имя поля значит совсем другое, версию протокола моста, а
    не версию пакета), и общий скан по нему тонет в чужих полях с тем же именем.

    `uv.lock` не сканируется этими же маркерами вовсе: в нём номер есть у каждого пакета
    зависимостей - легитимно и не про версию `torrcast`. Его запись сверяется отдельным,
    прицельным тестом выше.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    offenders: list[str] = []
    for name in tracked:
        path = REPO / name
        if path == UV_LOCK or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hit = False
        for line in text.splitlines():
            if _PY_MARKER.match(line) or _SHELL_MARKER.match(line) or _CLI_MARKER.match(line):
                hit = True
                break
            if path.name == "manifest.json" and _JSON_MARKER.match(line):
                hit = True
                break
        if hit and path not in KNOWN_VERSION_LOCATIONS:
            offenders.append(name)

    assert offenders == [], f"новое место с номером версии вне списка: {offenders}"
