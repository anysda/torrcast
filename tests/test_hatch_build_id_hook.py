"""`scripts/hatch_build_id_hook.py` (TC-1138): хэш `HEAD` внутри собранного колеса.

Обычная (не `-e`) установка `pip install <каталог>` - тем же способом ставят на стенды -
копирует файлы в колесо и `.git` с собой не берёт. Хук печатает хэш ДО того, как колесо
собрано. Гоняем настоящей сборкой hatchling (без pip и без сети - `hatchling` уже
установлен в тот же .venv, обычной сборочной изоляции тут не нужно) над маленьким
собственным git-репозиторием, по образцу заглушки в tests/test_release.py.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest
from hatchling.builders.wheel import WheelBuilder

REPO = Path(__file__).parents[1]
HOOK = REPO / "scripts" / "hatch_build_id_hook.py"
BUILD_ID_SOURCE = REPO / "torrcast" / "adapters" / "health" / "build_id.py"

_PYPROJECT = """\
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "torrcast"
dynamic = ["version"]
requires-python = ">=3.12"

[tool.hatch.version]
path = "torrcast/domain/version.py"

[tool.hatch.build.targets.wheel]
packages = ["torrcast"]

[tool.hatch.build.targets.wheel.hooks.custom]
path = "scripts/hatch_build_id_hook.py"
"""


def _committed_checkout(root: Path, version: str = "0.0.1") -> str:
    """Маленькое дерево с настоящей меткой и настоящим хуком, зафиксированное git'ом."""
    (root / "torrcast" / "domain").mkdir(parents=True)
    (root / "torrcast" / "domain" / "version.py").write_text(
        f'"""Версия."""\n\n__version__ = "{version}"\n', encoding="utf-8"
    )
    (root / "torrcast" / "adapters" / "health").mkdir(parents=True)
    shutil.copy(BUILD_ID_SOURCE, root / "torrcast" / "adapters" / "health" / "build_id.py")
    for package in ("torrcast", "torrcast/adapters", "torrcast/adapters/health", "torrcast/domain"):
        (root / package / "__init__.py").write_text("", encoding="utf-8")
    (root / "scripts").mkdir()
    shutil.copy(HOOK, root / "scripts" / "hatch_build_id_hook.py")
    (root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "test@test.test"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=root, check=True)
    head = subprocess.run(
        ["git", "rev-parse", "--short=12", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return head.stdout.strip()


@pytest.mark.machine
def test_a_plain_pip_style_wheel_build_carries_the_git_head(tmp_path: Path) -> None:
    """Колесо, собранное из каталога с `.git` (так ставят на стенды), несёт хэш `HEAD`."""
    checkout = tmp_path / "repo"
    checkout.mkdir()
    head = _committed_checkout(checkout)

    artifacts = list(WheelBuilder(str(checkout)).build(directory=str(tmp_path / "dist")))

    with zipfile.ZipFile(artifacts[0]) as wheel:
        baked = wheel.read("torrcast/adapters/health/build_id.py").decode("utf-8")
    assert f'BAKED_BUILD_ID: str | None = "{head}"' in baked


@pytest.mark.machine
def test_two_different_checkouts_bake_two_different_hashes(tmp_path: Path) -> None:
    """Ровно та же мера, что и на стенде: два разных коммита - две разные метки в колесе."""
    first = tmp_path / "first"
    first.mkdir()
    head_a = _committed_checkout(first, version="0.0.1")
    second = tmp_path / "second"
    second.mkdir()
    head_b = _committed_checkout(second, version="0.0.2")
    assert head_a != head_b

    wheel_a = next(WheelBuilder(str(first)).build(directory=str(tmp_path / "dist-a")))
    wheel_b = next(WheelBuilder(str(second)).build(directory=str(tmp_path / "dist-b")))

    with zipfile.ZipFile(wheel_a) as wheel:
        baked_a = wheel.read("torrcast/adapters/health/build_id.py").decode("utf-8")
    with zipfile.ZipFile(wheel_b) as wheel:
        baked_b = wheel.read("torrcast/adapters/health/build_id.py").decode("utf-8")
    assert head_a in baked_a
    assert head_b in baked_b
    assert baked_a != baked_b


def test_an_archive_without_git_leaves_the_placeholder_honest(tmp_path: Path) -> None:
    """Без `.git` вовсе (голый zip исходников) хук молчит - колесо несёт честный `None`."""
    checkout = tmp_path / "repo"
    checkout.mkdir()
    _committed_checkout(checkout)
    shutil.rmtree(checkout / ".git")

    artifacts = list(WheelBuilder(str(checkout)).build(directory=str(tmp_path / "dist")))

    with zipfile.ZipFile(artifacts[0]) as wheel:
        baked = wheel.read("torrcast/adapters/health/build_id.py").decode("utf-8")
    assert "BAKED_BUILD_ID: str | None = None" in baked
