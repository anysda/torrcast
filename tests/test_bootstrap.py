"""Ограждения бутстрапа `install` (TC-886): curl -fsSL .../ | sh тащит дерево сам.

Файл маленький и живёт в корне, отдельно от install.sh, поэтому и тесты - против
живого процесса и заглушки GitLab API (по образцу заглушки Prowlarr в
tests/test_install.py), а не разбором тела install.sh.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import subprocess
import tarfile
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import pytest

REPO = Path(__file__).parents[1]
BOOTSTRAP = REPO / "install"
SCRIPT = BOOTSTRAP.read_text(encoding="utf-8")


def _body(name: str) -> str:
    return SCRIPT.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def test_last_line_calls_main_and_nothing_follows() -> None:
    """🔴 Оборванная закачка не должна исполниться наполовину."""
    lines = SCRIPT.splitlines()
    assert lines[-1] == 'main "$@"'
    assert SCRIPT.count('main "$@"') == 1


def test_every_network_and_filesystem_action_lives_inside_a_function() -> None:
    """Вне функций - только shebang, комментарии, `set -eu`, переменные и сами
    определения функций. Ни один curl/tar/mkdir/rm не стоит на верхнем уровне."""
    depth = 0
    dangerous = ("curl ", "tar -", "mkdir ", "rm -rf", "sha256sum")
    for lineno, line in enumerate(SCRIPT.splitlines(), start=1):
        stripped = line.strip()
        if any(stripped.startswith(d) for d in dangerous):
            assert depth > 0, f"install:{lineno}: вне функции - {line!r}"
        depth += line.count("{") - line.count("}")
    assert depth == 0


def test_needs_curl_tar_sha256sum_before_touching_the_network() -> None:
    body = _body("main")
    assert "need curl" in body
    assert "need tar" in body
    assert "need sha256sum" in body
    assert body.index("need curl") < body.index("become_root")
    assert body.index("become_root") < body.index("latest_version")


def test_root_check_has_a_sandbox_escape_and_a_sudo_path_and_never_falls_through() -> None:
    body = _body("become_root")
    assert "TORRCAST_NO_ROOT" in body
    assert "exec sudo" in body
    assert 'fail "root is required:' in body
    assert '"нужен root:' in body


def test_a_404_before_the_first_release_speaks_plainly_instead_of_raw_json() -> None:
    body = _body("latest_version")
    assert "404)" in body
    assert "no releases yet" in body
    assert "fail " in body.split("404)", 1)[1].split(";;", 1)[0]


# --- заглушка GitLab: permalink/latest + generic-реестр ---------------------


def _tarball_bytes(install_body: str) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        data = install_body.encode()
        info = tarfile.TarInfo("install.sh")
        info.size = len(data)
        info.mode = 0o755  # как реальный install.sh (100755) после cp/tar в release.sh
        tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


_STUBS: list[ThreadingHTTPServer] = []


@pytest.fixture(autouse=True)
def _stop_stubs() -> Iterator[None]:
    yield
    for server in _STUBS:
        server.shutdown()
    _STUBS.clear()


def _stub_gitlab(
    tag: str | None,
    tarball: bytes | None,
    sha256_body: bytes | None,
    hits: dict[str, int] | None = None,
) -> int:
    """Заглушка на permalink/latest и generic-пакет, как настоящий GitLab: tag - тег
    С ведущей v (permalink/latest его так и отдаёт), а пакет и .sha256 живут ТОЛЬКО
    под голой версией (release.sh срезает v перед заливкой) - путь или имя файла с
    v в них ловят такой же 404, как в жизни, а не подыгрывают бутстрапу."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if hits is not None:
                hits[path] = hits.get(path, 0) + 1
            if path.endswith("/releases/permalink/latest"):
                if tag is None:
                    return self._send(404, {"message": "404 Not Found"})
                return self._send(200, {"tag_name": tag})
            bare = tag.removeprefix("v") if tag is not None else None
            prefix = f"/packages/generic/torrcast/{bare}/torrcast-{bare}.tar.gz"
            if tarball is not None and path.endswith(prefix):
                return self._send_bytes(200, tarball)
            if sha256_body is not None and path.endswith(f"{prefix}.sha256"):
                return self._send_bytes(200, sha256_body)
            return self._send(404, {"message": "нет такого"})

        def _send(self, code: int, payload: object) -> None:
            self._send_bytes(code, json.dumps(payload).encode())

        def _send_bytes(self, code: int, body: bytes) -> None:
            self.send_response(code)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _STUBS.append(server)
    return server.server_port


def _run_bootstrap(
    tmp_path: Path, port: int, extra_env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    mktmp = tmp_path / "mktmp"
    mktmp.mkdir()
    env = {
        **os.environ,
        "TMPDIR": str(mktmp),
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_GITLAB_API": f"http://127.0.0.1:{port}/api/v4",
        "TORRCAST_PROJECT_ID": "10",
        **(extra_env or {}),
    }
    return subprocess.run(
        ["sh", str(BOOTSTRAP)], capture_output=True, text=True, env=env, check=False
    )


@pytest.mark.machine
def test_no_release_yet_says_so_in_words_not_raw_404(tmp_path: Path) -> None:
    port = _stub_gitlab(tag=None, tarball=None, sha256_body=None)
    done = _run_bootstrap(tmp_path, port)
    assert done.returncode == 1
    assert "no releases yet" in done.stderr
    assert "come back after the first release" in done.stderr
    assert "{" not in done.stderr  # не сырой JSON в лицо
    assert not list((tmp_path / "mktmp").iterdir())  # прибрал за собой


@pytest.mark.machine
def test_a_good_release_downloads_verifies_and_hands_off_to_install_sh(
    tmp_path: Path,
) -> None:
    marker = tmp_path / "marker"
    stub_install = f"#!/usr/bin/env bash\n[[ -n x ]] && echo ran >> {marker}\nexit 0\n"
    tarball = _tarball_bytes(stub_install)
    digest = hashlib.sha256(tarball).hexdigest()
    sha_file = f"{digest}  torrcast-9.9.9.tar.gz\n".encode()

    port = _stub_gitlab(tag="v9.9.9", tarball=tarball, sha256_body=sha_file)
    done = _run_bootstrap(tmp_path, port)

    assert done.returncode == 0, done.stderr
    assert marker.read_text(encoding="utf-8") == "ran\n"
    assert not list((tmp_path / "mktmp").iterdir())


@pytest.mark.machine
def test_a_bad_checksum_dies_loud_and_never_runs_install_sh(tmp_path: Path) -> None:
    marker = tmp_path / "marker"
    stub_install = f"#!/usr/bin/env bash\n[[ -n x ]] && echo ran >> {marker}\nexit 0\n"
    tarball = _tarball_bytes(stub_install)
    wrong_sha = f"{'0' * 64}  torrcast-9.9.9.tar.gz\n".encode()

    port = _stub_gitlab(tag="v9.9.9", tarball=tarball, sha256_body=wrong_sha)
    done = _run_bootstrap(tmp_path, port)

    assert done.returncode != 0
    assert "sha256" in done.stderr and "mismatch" in done.stderr
    assert not marker.exists()
    assert not list((tmp_path / "mktmp").iterdir())


@pytest.mark.machine
def test_install_sh_exit_code_passes_through_without_a_bootstrap_wrapper(
    tmp_path: Path,
) -> None:
    """🔴 Код 2 (EXIT_INFRA/EXIT_CATALOG_CUT) - не отказ бутстрапа, а свой смысл
    install.sh. Бутстрап обязан вернуть его как есть, а не переодеть в «ошибка:»."""
    marker = tmp_path / "marker"
    stub_install = f"#!/usr/bin/env bash\n[[ -n x ]] && echo ran >> {marker}\nexit 2\n"
    tarball = _tarball_bytes(stub_install)
    digest = hashlib.sha256(tarball).hexdigest()
    sha_file = f"{digest}  torrcast-9.9.9.tar.gz\n".encode()

    port = _stub_gitlab(tag="v9.9.9", tarball=tarball, sha256_body=sha_file)
    done = _run_bootstrap(tmp_path, port)

    assert done.returncode == 2
    assert marker.read_text(encoding="utf-8") == "ran\n"
    assert "ошибка:" not in done.stderr


def _sudo_chain_bin(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Строит поддельные `id`, `sudo`, `curl`, как их видит бутстрап после `exec sudo`.

    `id` всегда говорит "не root". `sudo` ведёт себя как настоящий sudo без `-E` -
    записывает, что его позвали, и запускает переданную команду с ВЫТЕРТЫМ окружением
    (см. комментарий у become_root в install: TORRCAST_* не переживают -E на части
    машин). `curl` не ходит в сеть - вместо скачивания печатает щуп, который дописывает
    СВОЁ окружение (то, что реально досталось процессу за трубой) в файл. Это и есть
    замер поведением, а не грепом: наблюдаем то, что видит код после sudo, а не текст
    install."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    observed = tmp_path / "observed.txt"
    sudo_calls = tmp_path / "sudo_calls.txt"
    curl_calls = tmp_path / "curl_calls.txt"

    id_bin = bindir / "id"
    id_bin.write_text("#!/bin/sh\nprintf '1000\\n'\n", encoding="utf-8")
    id_bin.chmod(0o755)

    sudo_bin = bindir / "sudo"
    sudo_bin.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{sudo_calls}"\n'
        'exec env -i PATH="$PATH" HOME="$HOME" "$@"\n',
        encoding="utf-8",
    )
    sudo_bin.chmod(0o755)

    curl_bin = bindir / "curl"
    curl_bin.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{curl_calls}"\n'
        "cat <<'PROBE'\n"
        "#!/bin/sh\n"
        "{\n"
        '  printf "LANGUAGE=%s\\n" "${TORRCAST_LANGUAGE:-<unset>}"\n'
        '  printf "BOOTSTRAP_URL=%s\\n" "${TORRCAST_BOOTSTRAP_URL:-<unset>}"\n'
        f'}} >> "{observed}"\n'
        "PROBE\n",
        encoding="utf-8",
    )
    curl_bin.chmod(0o755)

    return bindir, observed, sudo_calls, curl_calls


@pytest.mark.machine
@pytest.mark.parametrize("language", ["ru", "en"])
def test_language_survives_the_restart_through_sudo(tmp_path: Path, language: str) -> None:
    """Дыра TC-886/2: `TORRCAST_LANGUAGE` в become_root доезжает до перезапущенного
    процесса ТОЛЬКО через явный export внутри `sh -c` за sudo - окружение самого sudo
    настоящий sudo без `-E` вытирает молча. Замер не грепает install, а сажает щуп
    именно там, куда попадает то, что бутстрап зовёт ПОСЛЕ sudo, и печатает
    наблюдённое окружение. Без TORRCAST_NO_ROOT (та лазейка пропускает ровно этот путь):
    не-root изображён поддельным `id`."""
    bindir, observed, sudo_calls, curl_calls = _sudo_chain_bin(tmp_path)
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "TORRCAST_LANGUAGE": language}
    env.pop("TORRCAST_NO_ROOT", None)

    done = subprocess.run(
        ["sh", str(BOOTSTRAP)], capture_output=True, text=True, env=env, check=False
    )

    assert sudo_calls.exists() and sudo_calls.read_text(encoding="utf-8").strip(), (
        f"sudo ни разу не был позван - нечего мерить (stderr: {done.stderr!r})"
    )
    assert curl_calls.exists() and curl_calls.read_text(encoding="utf-8").strip(), (
        f"curl за sudo ни разу не был позван - нечего мерить (stderr: {done.stderr!r})"
    )
    assert observed.exists() and observed.read_text(encoding="utf-8").strip(), (
        "щуп ничего не увидел: ноль наблюдений за трубой sudo -> curl -> sh, "
        f"судить о языке нечем (stderr: {done.stderr!r})"
    )
    body = observed.read_text(encoding="utf-8")
    assert f"LANGUAGE={language}" in body, (
        f"TORRCAST_LANGUAGE не пережил перезапуск через sudo: ждали {language!r}, "
        f"щуп увидел {body!r}"
    )


@pytest.mark.machine
def test_the_tag_from_permalink_is_stripped_of_v_before_hitting_the_registry(
    tmp_path: Path,
) -> None:
    """TC-886, регресс v0.99.99: permalink/latest отдаёт тег С ведущей v, а
    generic-реестр (release.sh) кладёт пакет БЕЗ неё. Если install снова подставит
    сырой тег в путь реестра или в имя файла, заглушка (как настоящий GitLab)
    ответит 404, и установка упадёт."""
    marker = tmp_path / "marker"
    stub_install = f"#!/usr/bin/env bash\n[[ -n x ]] && echo ran >> {marker}\nexit 0\n"
    tarball = _tarball_bytes(stub_install)
    digest = hashlib.sha256(tarball).hexdigest()
    sha_file = f"{digest}  torrcast-9.9.9.tar.gz\n".encode()

    port = _stub_gitlab(tag="v9.9.9", tarball=tarball, sha256_body=sha_file)
    done = _run_bootstrap(tmp_path, port)

    assert done.returncode == 0, done.stderr
    assert marker.read_text(encoding="utf-8") == "ran\n"
