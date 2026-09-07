"""Проверяет метку кода: клеймо тарбола, живой git и честное «неоткуда узнать»."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from torrcast.adapters.health import build_id as build_id_module
from torrcast.adapters.health.build_id import build_id


def _committed(root: Path) -> str:
    """Заводит однокоммитный git-репозиторий в `root`, отдаёт короткий хэш ``HEAD``."""
    subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "f.txt").write_text("1")
    subprocess.run(["git", "add", "f.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--quiet", "-m", "init"], cwd=root, check=True)
    return subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--short=12", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_a_baked_stamp_wins_over_git(monkeypatch: pytest.MonkeyPatch) -> None:
    """Тарбол выпуска сказал своё - живой git этого дерева уже не спрашивается."""
    monkeypatch.setattr(build_id_module, "BAKED_BUILD_ID", "cafef00dfeed")
    assert build_id() == "cafef00dfeed"


@pytest.mark.machine
def test_a_clean_git_checkout_answers_with_its_head(tmp_path: Path) -> None:
    """Чекаут без клейма отвечает своим ``HEAD``, без пометки «грязно»."""
    repo = tmp_path / "repo"
    repo.mkdir()
    head = _committed(repo)

    stamp = build_id_module._git_build_id(repo)

    assert stamp == head
    assert "+dirty" not in (stamp or "")


@pytest.mark.machine
def test_an_uncommitted_change_marks_the_checkout_dirty(tmp_path: Path) -> None:
    """Незакоммиченная правка отвечает тем же хэшем, но с пометкой «грязно»."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _committed(repo)
    (repo / "f.txt").write_text("2")

    stamp = build_id_module._git_build_id(repo)

    assert stamp is not None
    assert stamp.endswith("+dirty")


def test_no_git_and_no_stamp_is_an_honest_unknown(tmp_path: Path) -> None:
    """Ни клейма, ни git - ``None``, а не выдуманное значение."""
    empty = tmp_path / "not-a-repo"
    empty.mkdir()
    assert build_id_module._git_build_id(empty) is None
