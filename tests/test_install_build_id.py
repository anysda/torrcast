"""Mirror for the installer's venv check on a package built from a git checkout.

The wheel hook (``scripts/hatch_build_id_hook.py``) writes the ``HEAD`` hash into the venv
copy of ``build_id.py`` whenever the tree carries ``.git``, so ``git clone`` + ``install.sh``
from the README died on its own honest package: "venv does not match the sources".
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests.test_install import _funcs

_MARK = "adapters/health/build_id.py"
_PLACEHOLDER = "BAKED_BUILD_ID: str | None = None\n"


def _package(root: Path, mark: str) -> Path:
    (root / "adapters" / "health").mkdir(parents=True)
    (root / "__init__.py").write_text("", encoding="utf-8")
    (root / _MARK).write_text(f'"""Build mark."""\n\n{mark}', encoding="utf-8")
    return root


def _manifest(tree: Path) -> str:
    done = subprocess.run(
        [
            "bash",
            "-c",
            f'{_funcs("py_manifest", "unbaked_digest")}\npy_manifest "$1"',
            "bash",
            str(tree),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    return done.stdout


@pytest.mark.machine
def test_a_wheel_built_from_a_checkout_matches_its_tree(tmp_path: Path) -> None:
    """Rollback (``py_manifest`` hashing the file as is): the baked hash reads as a stale venv."""
    tree = _package(tmp_path / "tree", _PLACEHOLDER)
    venv = _package(tmp_path / "venv", 'BAKED_BUILD_ID: str | None = "a4f5c43d0e1f"\n')
    assert _manifest(tree) == _manifest(venv)
    assert f"./{_MARK}" in _manifest(tree)


@pytest.mark.machine
def test_any_other_change_to_the_build_mark_still_differs(tmp_path: Path) -> None:
    """Only the stamp is forgiven: a stale copy of the rest of the file is still caught."""
    tree = _package(tmp_path / "tree", _PLACEHOLDER)
    venv = _package(tmp_path / "venv", _PLACEHOLDER + "STALE = 1\n")
    assert _manifest(tree) != _manifest(venv)


@pytest.mark.machine
@pytest.mark.parametrize(
    "stamp",
    ['__import__("os").system("id")', '"abc"; STALE = 1', '"a4f5c43d0e1f"; STALE = 1'],
)
def test_only_a_git_hash_is_forgiven_as_the_stamp(tmp_path: Path, stamp: str) -> None:
    """Rollback (the whole stamp line forgiven): code smuggled into the stamp reads as clean."""
    tree = _package(tmp_path / "tree", _PLACEHOLDER)
    venv = _package(tmp_path / "venv", f"BAKED_BUILD_ID: str | None = {stamp}\n")
    assert _manifest(tree) != _manifest(venv)
