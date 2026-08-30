"""Ограждения `scripts/release.sh` (TC-886): шесть шагов публикации релиза.

Гоняем как процесс против собственного маленького git-репозитория (клон - по
контракту скрипта - ПО ТЕГУ, не рабочее дерево) и заглушки GitLab API, по образцу
заглушки Prowlarr в tests/test_install.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tarfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).parents[1]
RELEASE_SH = REPO / "scripts" / "release.sh"


def _write_repo(root: Path) -> None:
    (root / "torrcast" / "domain").mkdir(parents=True)
    (root / "torrcast" / "domain" / "version.py").write_text(
        '"""Версия."""\n\n__version__ = "0.1.0"\n', encoding="utf-8"
    )
    (root / "tgbot").mkdir()
    (root / "tgbot" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "torrcast"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    (root / "install.sh").write_text("#!/usr/bin/env bash\nVERSION='0.1.0'\n", encoding="utf-8")
    (root / "install").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    (root / "README.md").write_text("# torrcast\n", encoding="utf-8")
    (root / "LICENSE").write_text("MIT\n", encoding="utf-8")
    scripts = root / "scripts"
    scripts.mkdir()
    for name in (
        "sni-shim.py",
        "anilibria.yml",
        "jacred.yml",
        "anilibria-indexer.py",
        "jacred-indexer.py",
    ):
        (scripts / name).write_text("stub\n", encoding="utf-8")


def _git(cwd: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
        env={
            **os.environ,
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
        },
    )
    return done.stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """master с тегом v9.9.9 на верхушке - счастливый путь."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "--quiet", "-b", "master")
    _write_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", "seed")
    _git(root, "tag", "v9.9.9")
    return root


@pytest.fixture
def repo_tag_off_master(tmp_path: Path) -> Path:
    """Тег стоит на ветке, которой в master нет."""
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "--quiet", "-b", "master")
    _write_repo(root)
    _git(root, "add", "-A")
    _git(root, "commit", "--quiet", "-m", "seed")
    _git(root, "checkout", "--quiet", "-b", "feature")
    (root / "README.md").write_text("# feature\n", encoding="utf-8")
    _git(root, "commit", "--quiet", "-am", "off master")
    _git(root, "tag", "v9.9.9")
    _git(root, "checkout", "--quiet", "master")
    return root


def _run(
    tag: str,
    *,
    dry_run: bool = True,
    repo_path: Path | None = None,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    args = ["--dry-run", tag] if dry_run else [tag]
    env = {**os.environ, **(extra_env or {})}
    if repo_path is not None:
        env["TORRCAST_GITLAB_REPO"] = str(repo_path)
    return subprocess.run(
        [str(RELEASE_SH), *args], capture_output=True, text=True, env=env, check=False
    )


@pytest.mark.machine
def test_no_tag_dies_with_usage() -> None:
    done = subprocess.run([str(RELEASE_SH)], capture_output=True, text=True, check=False)
    assert done.returncode != 0
    assert "нужен тег" in done.stderr


@pytest.mark.machine
def test_unknown_flag_dies() -> None:
    done = subprocess.run(
        [str(RELEASE_SH), "--bogus", "v1.0.0"], capture_output=True, text=True, check=False
    )
    assert done.returncode != 0
    assert "неизвестный флаг" in done.stderr


@pytest.mark.machine
def test_a_non_semver_tag_is_rejected_before_touching_the_network() -> None:
    """Формат тега проверяется ПЕРВЫМ шагом - до клона, значит и до сети."""
    done = _run("v1.0", repo_path=Path("/nonexistent/unreachable.git"))
    assert done.returncode != 0
    assert "не semver" in done.stderr


@pytest.mark.machine
def test_a_tag_off_master_is_rejected(repo_tag_off_master: Path) -> None:
    done = _run("v9.9.9", repo_path=repo_tag_off_master)
    assert done.returncode != 0
    assert "не лежит на master" in done.stderr


@pytest.mark.machine
def test_dry_run_does_steps_1_to_4_for_real_and_prints_5_and_6(repo: Path) -> None:
    done = _run(
        "v9.9.9",
        repo_path=repo,
        extra_env={"TORRCAST_GITLAB_API": "http://127.0.0.1:1/api/v4"},
    )
    assert done.returncode == 0, done.stderr
    out = done.stdout + done.stderr
    assert "[1]" in out and "[2]" in out and "[3]" in out and "[4]" in out
    assert "не выполняю" in out
    assert "оставлены на диске" in out

    work = out.split("оставлены на диске: ", 1)[1].split(" -", 1)[0].strip()
    tar_path = Path(work) / "torrcast-9.9.9.tar.gz"
    sha_path = Path(work) / "torrcast-9.9.9.tar.gz.sha256"
    assert tar_path.is_file()
    assert sha_path.is_file()

    digest = hashlib.sha256(tar_path.read_bytes()).hexdigest()
    assert digest in sha_path.read_text(encoding="utf-8")

    with tarfile.open(tar_path) as tar:
        names = tar.getnames()
        assert "torrcast/domain/version.py" in names
        assert "pyproject.toml" in names
        assert "install.sh" in names
        assert "tests" not in names and not any(n.startswith("tests/") for n in names)

        version_py = tar.extractfile("torrcast/domain/version.py")
        assert version_py is not None
        assert '__version__ = "9.9.9"' in version_py.read().decode()

        pyproject = tar.extractfile("pyproject.toml")
        assert pyproject is not None
        assert 'version = "9.9.9"' in pyproject.read().decode()

        install_sh = tar.extractfile("install.sh")
        assert install_sh is not None
        assert "VERSION='9.9.9'" in install_sh.read().decode()

    import shutil

    shutil.rmtree(work, ignore_errors=True)


@pytest.mark.machine
def test_real_run_without_a_token_dies_before_any_upload(repo: Path) -> None:
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITLAB_API": "http://127.0.0.1:1/api/v4",
            "GITLAB_TOKEN": "",
            "CI_JOB_TOKEN": "",
        },
    )
    assert done.returncode != 0
    assert "нужен токен" in done.stderr


# --- заглушка GitLab: реальная заливка и релиз -------------------------------

_STUBS: list[ThreadingHTTPServer] = []


@pytest.fixture(autouse=True)
def _stop_stubs() -> Iterator[None]:
    yield
    for server in _STUBS:
        server.shutdown()
    _STUBS.clear()


class _Seen:
    """Что заглушка увидела: заливки, заголовок токена и тело созданного релиза
    (последнее - разобранный JSON, оттого Any: ключи знает только сам тест)."""

    def __init__(self) -> None:
        self.uploads: list[str] = []
        self.auth: list[str | None] = []
        self.release: Any = None


def _stub_gitlab_write() -> tuple[int, _Seen]:
    seen = _Seen()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def _send(self, code: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_PUT(self) -> None:
            seen.auth.append(self.headers.get("PRIVATE-TOKEN") or self.headers.get("JOB-TOKEN"))
            length = int(self.headers.get("Content-Length") or 0)
            self.rfile.read(length)
            seen.uploads.append(urlparse(self.path).path)
            return self._send(201, {})

        def do_POST(self) -> None:
            if not urlparse(self.path).path.endswith("/releases"):
                return self._send(404, {"message": "нет такого"})
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            seen.release = body
            return self._send(201, body)

        def do_GET(self) -> None:
            if urlparse(self.path).path.endswith("/releases/permalink/latest"):
                if seen.release is None:
                    return self._send(404, {"message": "404 Not Found"})
                return self._send(200, {"tag_name": seen.release["tag_name"]})
            return self._send(404, {"message": "нет такого"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _STUBS.append(server)
    return server.server_port, seen


@pytest.mark.machine
def test_a_real_run_uploads_the_asset_pair_and_publishes_a_release(repo: Path) -> None:
    port, seen = _stub_gitlab_write()
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITLAB_API": f"http://127.0.0.1:{port}/api/v4",
            "TORRCAST_GITLAB_WEB": f"http://127.0.0.1:{port}",
            "GITLAB_TOKEN": "s3cr3t",
        },
    )
    assert done.returncode == 0, done.stderr
    assert "готово" in done.stdout + done.stderr

    uploads = seen.uploads
    assert any(p.endswith("torrcast-9.9.9.tar.gz") for p in uploads)
    assert any(p.endswith("torrcast-9.9.9.tar.gz.sha256") for p in uploads)
    assert all(a == "s3cr3t" for a in seen.auth)

    release = seen.release
    assert release["tag_name"] == "v9.9.9"
    links = release["assets"]["links"]
    install_link = next(link for link in links if link["name"] == "install")
    tarball_link = next(link for link in links if link["name"] == "tarball")
    assert install_link["filepath"] == "/install"
    assert "torrcast-9.9.9.tar.gz" in tarball_link["url"]


@pytest.mark.machine
def test_a_ci_job_token_is_sent_as_job_token_header(repo: Path) -> None:
    port, seen = _stub_gitlab_write()
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITLAB_API": f"http://127.0.0.1:{port}/api/v4",
            "TORRCAST_GITLAB_WEB": f"http://127.0.0.1:{port}",
            "CI_JOB_TOKEN": "ci-token",
        },
    )
    assert done.returncode == 0, done.stderr
    assert all(a == "ci-token" for a in seen.auth)
