"""Ограждения `scripts/release.sh` (TC-886): шесть шагов публикации релиза.

Гоняем как процесс против собственного маленького git-репозитория (клон - по
контракту скрипта - ПО ТЕГУ, не рабочее дерево) и заглушки GitHub, по образцу
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
from urllib.parse import parse_qs, urlparse

import pytest

REPO = Path(__file__).parents[1]
RELEASE_SH = REPO / "scripts" / "release.sh"


def _write_repo(root: Path) -> None:
    (root / "torrcast" / "domain").mkdir(parents=True)
    (root / "torrcast" / "domain" / "version.py").write_text(
        '"""Версия."""\n\n__version__ = "1.0.0"\n', encoding="utf-8"
    )
    (root / "tgbot").mkdir()
    (root / "tgbot" / "__init__.py").write_text("", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "torrcast"\nversion = "1.0.0"\n', encoding="utf-8"
    )
    (root / "install.sh").write_text("#!/usr/bin/env bash\nVERSION='1.0.0'\n", encoding="utf-8")
    os.chmod(root / "install.sh", 0o755)  # как реальный install.sh в репе (100755)
    (root / "install").write_text("#!/bin/sh\ntrue\n", encoding="utf-8")
    (root / "README.md").write_text("# torrcast\n", encoding="utf-8")
    for tongue in ("jp", "es", "ru"):
        (root / f"README-{tongue}.md").write_text(f"# torrcast ({tongue})\n", encoding="utf-8")
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
    notes: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    args = ["--dry-run", tag] if dry_run else [tag]
    if notes is not None:
        args = ["--notes", str(notes), *args]
    env = {**os.environ, **(extra_env or {})}
    if repo_path is not None:
        env["TORRCAST_GITHUB_REPO"] = str(repo_path)
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
def test_notes_without_a_file_dies_before_touching_the_network(tmp_path: Path) -> None:
    """Описание релиза пишется один раз и вручную: опечатка в пути к нему обязана
    остановить выпуск, а не завести релиз с пустым телом."""
    done = subprocess.run(
        [str(RELEASE_SH), "--notes", str(tmp_path / "нет-такого.md"), "v9.9.9"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode != 0
    assert "файла с описанием нет" in done.stderr


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
        extra_env={"TORRCAST_GITHUB_API": "http://127.0.0.1:1"},
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
        # Английский README ссылается на три перевода: уехавший без них ведёт
        # установленную копию на файлы, которых в ней нет.
        assert {"README.md", "README-jp.md", "README-es.md", "README-ru.md"} <= set(names)
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
        # +x должен доехать до тарбола: install (TC-886) зовёт install.sh его
        # собственным шебангом, не через `sh`, и без исполняемого бита это упадёт.
        assert tar.getmember("install.sh").mode & 0o111, "install.sh в тарболе не +x"

    import shutil

    shutil.rmtree(work, ignore_errors=True)


@pytest.mark.machine
def test_real_run_without_a_token_dies_before_any_upload(repo: Path) -> None:
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITHUB_API": "http://127.0.0.1:1",
            "GITHUB_TOKEN": "",
        },
    )
    assert done.returncode != 0
    assert "нужен токен" in done.stderr


# --- заглушка GitHub: реальная заливка и релиз -------------------------------

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


# Id созданного релиза. Намеренно НЕ совпадает с чужими id в том же ответе (author),
# и намеренно меньше их: разбор по первому совпадению возьмёт чужой и промахнётся.
_RELEASE_ID = 7


def _stub_github_write() -> tuple[int, _Seen]:
    """Заглушка на создание релиза, заливку ассетов и `/releases/latest`.

    Формы взяты с живого GitHub: релиз заводится POST'ом на `/releases` и отвечает
    телом с числовым `id`; ассет льётся POST'ом на `/releases/<id>/assets?name=ИМЯ`,
    а имя приезжает В ЗАПРОСЕ, а не в теле; `/releases/latest` не отдаёт JSON, а
    перенаправляет на `/releases/tag/<тег>`.

    🔴 `id` намеренно НЕ первое поле ответа и рядом лежат чужие `id`: разбор по
    первому попавшемуся (sed, регулярка) обязан здесь сломаться, а не подыграть."""
    seen = _Seen()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def _send(self, code: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length)
            seen.auth.append(self.headers.get("Authorization"))

            if parsed.path.endswith("/assets"):
                if seen.release is None:
                    return self._send(404, {"message": "релиза ещё нет"})
                # 🔴 Ассет кладётся В РЕЛИЗ, и живой GitHub на чужой id отвечает 404,
                # а не молча принимает файл в никуда. Заглушка, глядящая только на
                # хвост `/assets`, пропустила бы разбор ответа по первому попавшемуся
                # "id" (в теле их несколько) - проверено отрицательной пробой.
                want = f"/releases/{_RELEASE_ID}/assets"
                if not parsed.path.endswith(want):
                    return self._send(404, {"message": f"нет релиза по пути {parsed.path}"})
                name = parse_qs(parsed.query).get("name", [""])[0]
                seen.uploads.append(name)
                return self._send(201, {"name": name})

            if not parsed.path.endswith("/releases"):
                return self._send(404, {"message": "нет такого"})
            body = json.loads(raw or b"{}")
            seen.release = body
            return self._send(201, {"author": {"id": 4242}, "url": "…", **body, "id": _RELEASE_ID})

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if path.endswith("/releases/latest"):
                base = path[: -len("/latest")]
                if seen.release is None:
                    return self._redirect(base)
                return self._redirect(f"{base}/tag/{seen.release['tag_name']}")
            return self._send(404, {"message": "нет такого"})

        def _redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _STUBS.append(server)
    return server.server_port, seen


@pytest.mark.machine
def test_a_real_run_uploads_the_asset_pair_and_publishes_a_release(repo: Path) -> None:
    port, seen = _stub_github_write()
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITHUB_API": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_WEB": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_UPLOADS": f"http://127.0.0.1:{port}",
            "GITHUB_TOKEN": "s3cr3t",
        },
    )
    assert done.returncode == 0, done.stderr
    assert "готово" in done.stdout + done.stderr

    # 🔴 Имена ассетов - часть адресов, по которым за релизом приходят снаружи.
    # `install` держит короткий адрес установщика (`releases/latest/download/install`),
    # а пара тарбол+sha256 - то, что бутстрап тащит и сверяет. Промах в имени
    # ломает установку молча, поэтому имена сверяются целиком, а не по «есть три».
    assert set(seen.uploads) == {
        "torrcast-9.9.9.tar.gz",
        "torrcast-9.9.9.tar.gz.sha256",
        "install",
    }
    assert all(a == "Bearer s3cr3t" for a in seen.auth)
    assert seen.release["tag_name"] == "v9.9.9"


@pytest.mark.machine
def test_the_token_travels_as_a_bearer_header_on_every_write(repo: Path) -> None:
    """Токен обязан ехать на КАЖДОЙ пишущей ходке, а не только на создании релиза:
    заливка ассетов идёт на другой хост (uploads.github.com), и потерять заголовок
    именно там - отдельный способ получить релиз без единого файла."""
    port, seen = _stub_github_write()
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITHUB_API": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_WEB": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_UPLOADS": f"http://127.0.0.1:{port}",
            "GITHUB_TOKEN": "s3cr3t",
        },
    )
    assert done.returncode == 0, done.stderr
    assert len(seen.auth) == 4, f"ждали релиз + три ассета, видели {len(seen.auth)}"
    assert all(a == "Bearer s3cr3t" for a in seen.auth)


@pytest.mark.machine
def test_notes_land_in_the_release_description_verbatim(repo: Path, tmp_path: Path) -> None:
    """Описание едет в релиз как есть: с кавычками, переводами строк и кириллицей.
    Склейка тела руками ломалась бы на первой же цитате."""
    notes = tmp_path / "notes.md"
    text = '## torrcast 1.0.0\n\nСтрока с "кавычками", обратным слешем \\ и переносом.\n'
    notes.write_text(text, encoding="utf-8")

    port, seen = _stub_github_write()
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        notes=notes,
        extra_env={
            "TORRCAST_GITHUB_API": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_WEB": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_UPLOADS": f"http://127.0.0.1:{port}",
            "GITHUB_TOKEN": "s3cr3t",
        },
    )
    assert done.returncode == 0, done.stderr
    assert seen.release["body"] == text


@pytest.mark.machine
def test_without_notes_the_release_carries_no_description(repo: Path) -> None:
    """Отрицательная проба к предыдущему тесту: описание берётся из флага, а не
    появляется само. Без флага ключа нет, и прежнее тело релиза не переписывается."""
    port, seen = _stub_github_write()
    done = _run(
        "v9.9.9",
        dry_run=False,
        repo_path=repo,
        extra_env={
            "TORRCAST_GITHUB_API": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_WEB": f"http://127.0.0.1:{port}",
            "TORRCAST_GITHUB_UPLOADS": f"http://127.0.0.1:{port}",
            "GITHUB_TOKEN": "s3cr3t",
        },
    )
    assert done.returncode == 0, done.stderr
    assert "body" not in seen.release
