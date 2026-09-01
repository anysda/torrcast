"""Ограждения бутстрапа `install` (TC-886): curl -fsSL .../ | sh тащит дерево сам.

Файл маленький и живёт в корне, отдельно от install.sh, поэтому и тесты - против
живого процесса и заглушки GitHub (по образцу заглушки Prowlarr в
tests/test_install.py), а не разбором тела install.sh.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
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
INSTALLER = (REPO / "install.sh").read_text(encoding="utf-8")


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


def test_no_release_yet_is_told_apart_from_a_working_one_by_the_tag_in_the_location() -> None:
    """До первого релиза `/releases/latest` уводит не на `/releases/tag/...`, а на
    список релизов. Разбор идёт по `*/releases/tag/*`, и только эта ветка считается
    рабочей: без неё «релизов нет» и «GitHub ответил не так» слиплись бы в один путь."""
    body = _body("latest_version")
    assert "*/releases/tag/*)" in body
    assert "no releases yet" in body
    tail = body.split("*/releases/tag/*)", 1)[1]
    assert "fail " in tail


def test_the_version_is_learned_without_touching_the_rate_limited_api() -> None:
    """🔴 У анонима на api.github.com 60 запросов в час НА АДРЕС, и за одним NAT этот
    потолок общий. Бутстрап обязан спрашивать версию у обычного `/releases/latest`,
    который перенаправляет, а не у API.

    Судим по КОДУ, а не по всему файлу: комментарий рядом объясняет, почему API здесь
    не зовут, и назвал бы адрес сам - проба ловила бы собственное объяснение."""
    code = "\n".join(line for line in SCRIPT.splitlines() if not line.lstrip().startswith("#"))
    assert "api.github.com" not in code
    assert "/releases/latest" in _body("latest_version")


# --- заглушка GitHub: releases/latest + ассеты релиза -----------------------


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


def _stub_github(
    tag: str | None,
    tarball: bytes | None,
    sha256_body: bytes | None,
    hits: dict[str, int] | None = None,
) -> int:
    """Заглушка на `/releases/latest` и ассеты релиза, как настоящий GitHub.

    `/releases/latest` не отдаёт тело, а перенаправляет: есть релиз - на
    `/releases/tag/<tag>`, нет ни одного - на `/releases`. Обе формы взяты с живого
    github.com, а не придуманы.

    tag - С ведущей v (так он стоит и в Location, и в пути ассета), а имена самих
    файлов - ТОЛЬКО под голой версией (release.sh срезает v перед заливкой): путь или
    имя файла с v в них ловят такой же 404, как в жизни, а не подыгрывают бутстрапу."""

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            return

        def do_GET(self) -> None:
            path = urlparse(self.path).path
            if hits is not None:
                hits[path] = hits.get(path, 0) + 1
            if path.endswith("/releases/latest"):
                base = path[: -len("/latest")]
                where = f"{base}/tag/{tag}" if tag is not None else base
                return self._redirect(where)
            bare = tag.removeprefix("v") if tag is not None else None
            prefix = f"/releases/download/{tag}/torrcast-{bare}.tar.gz"
            if tarball is not None and path.endswith(prefix):
                return self._send_bytes(200, tarball)
            if sha256_body is not None and path.endswith(f"{prefix}.sha256"):
                return self._send_bytes(200, sha256_body)
            return self._send(404, {"message": "нет такого"})

        def _redirect(self, location: str) -> None:
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

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
    tmp_path: Path,
    port: int,
    extra_env: dict[str, str] | None = None,
    sealed: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Прогон загрузчика против заглушки GitHub.

    ``sealed`` запирает временный каталог на запись: тогда любой ``mktemp -d`` под
    ``set -eu`` роняет заход с ненулевым кодом. Это мера ОТСУТСТВИЯ работы, а не
    опрятности: пустой каталог одинаково выходит и у того, кто ничего не делал, и у
    того, кто прибрал за собой.
    """
    mktmp = tmp_path / "mktmp"
    mktmp.mkdir()
    if sealed:
        mktmp.chmod(0o555)
    env = {
        **os.environ,
        "TMPDIR": str(mktmp),
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_GITHUB_WEB": f"http://127.0.0.1:{port}",
        "TORRCAST_PROJECT_PATH": "anysda/torrcast",
        **(extra_env or {}),
    }
    try:
        return subprocess.run(
            ["sh", str(BOOTSTRAP)], capture_output=True, text=True, env=env, check=False
        )
    finally:
        if sealed:
            mktmp.chmod(0o755)


@pytest.mark.machine
def test_no_release_yet_says_so_in_words_not_a_bare_redirect(tmp_path: Path) -> None:
    port = _stub_github(tag=None, tarball=None, sha256_body=None)
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

    port = _stub_github(tag="v9.9.9", tarball=tarball, sha256_body=sha_file)
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

    port = _stub_github(tag="v9.9.9", tarball=tarball, sha256_body=wrong_sha)
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

    port = _stub_github(tag="v9.9.9", tarball=tarball, sha256_body=sha_file)
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
def test_the_tag_is_stripped_of_v_in_the_file_name_but_not_in_the_path(
    tmp_path: Path,
) -> None:
    """TC-886, регресс: тег едет С ведущей v в ПУТЬ ассета и БЕЗ неё в ИМЯ файла
    (release.sh собирает имена по голой версии). Обе половины разъезжаются в разные
    стороны, и если install подставит одну форму в оба места, заглушка (как настоящий
    GitHub) ответит 404, и установка упадёт."""
    marker = tmp_path / "marker"
    stub_install = f"#!/usr/bin/env bash\n[[ -n x ]] && echo ran >> {marker}\nexit 0\n"
    tarball = _tarball_bytes(stub_install)
    digest = hashlib.sha256(tarball).hexdigest()
    sha_file = f"{digest}  torrcast-9.9.9.tar.gz\n".encode()

    port = _stub_github(tag="v9.9.9", tarball=tarball, sha256_body=sha_file)
    done = _run_bootstrap(tmp_path, port)

    assert done.returncode == 0, done.stderr
    assert marker.read_text(encoding="utf-8") == "ran\n"


@pytest.mark.machine
def test_the_same_version_is_named_latest_without_touching_a_single_file(
    tmp_path: Path,
) -> None:
    """🔴 Второй вход (TC-887): установлено ровно то, что выпущено - работы нет ВОВСЕ.

    Проверяется не слово на экране, а отсутствие работы: заглушку спросили один раз, за
    тегом, и ни за тарболом, ни за сверкой к ней не пришли.

    🔴 Временный каталог тут ЗАПЕРТ на запись, и это не придирка. Прежняя мера смотрела,
    что каталог пуст, - и покупалась ранним выходом, переставленным ПОСЛЕ ``mktemp -d``
    с ``trap rm -rf``: прибрал за собой, и зелено. Именно так эту меру и купили при
    разборе. Запертый каталог такой покупки не принимает: ``mktemp -d`` в нём не
    заводится вовсе, и заход падает ненулевым кодом.
    """
    marker = tmp_path / "marker"
    stub_install = f"#!/usr/bin/env bash\necho ran >> {marker}\nexit 0\n"
    tarball = _tarball_bytes(stub_install)
    digest = hashlib.sha256(tarball).hexdigest()
    hits: dict[str, int] = {}

    port = _stub_github(
        tag="v9.9.9",
        tarball=tarball,
        sha256_body=f"{digest}  torrcast-9.9.9.tar.gz\n".encode(),
        hits=hits,
    )
    done = _run_bootstrap(tmp_path, port, {"TORRCAST_UPGRADE_FROM": "9.9.9"}, sealed=True)

    assert done.returncode == 0, done.stderr
    assert "9.9.9 is already the latest version" in done.stderr
    assert not marker.exists(), "установщик всё-таки позвали"
    assert not list((tmp_path / "mktmp").iterdir())
    assert list(hits) == ["/anysda/torrcast/releases/latest"], hits


@pytest.mark.machine
def test_a_newer_version_names_the_move_and_tells_the_installer_where_it_came_from(
    tmp_path: Path,
) -> None:
    """Переход называется человеку, а установщику - версия, от которой идём.

    Второе важнее первого: ровно по этой переменной install.sh рисует заставку
    обновления вместо заставки установки, и без неё человек получил бы «установлено»
    там, где его обновили.
    """
    marker = tmp_path / "marker"
    stub_install = (
        f'#!/usr/bin/env bash\necho "from ${{TORRCAST_UPGRADE_FROM:-нет}}" >> {marker}\nexit 0\n'
    )
    tarball = _tarball_bytes(stub_install)
    digest = hashlib.sha256(tarball).hexdigest()

    port = _stub_github(
        tag="v9.9.9",
        tarball=tarball,
        sha256_body=f"{digest}  torrcast-9.9.9.tar.gz\n".encode(),
    )
    done = _run_bootstrap(tmp_path, port, {"TORRCAST_UPGRADE_FROM": "1.0.0"})

    assert done.returncode == 0, done.stderr
    assert "torrcast 1.0.0 → 9.9.9" in done.stderr
    assert marker.read_text(encoding="utf-8") == "from 1.0.0\n"


@pytest.mark.machine
def test_the_upgrade_speaks_the_tongue_it_was_given(tmp_path: Path) -> None:
    port = _stub_github(tag="v9.9.9", tarball=None, sha256_body=None)
    done = _run_bootstrap(
        tmp_path, port, {"TORRCAST_UPGRADE_FROM": "9.9.9", "TORRCAST_LANGUAGE": "ru"}
    )

    assert done.returncode == 0, done.stderr
    assert "torrcast 9.9.9 - уже последняя версия" in done.stderr


@pytest.mark.skipif(os.geteuid() == 0, reason="под root отказа по правам не бывает")
@pytest.mark.machine
def test_an_upgrade_without_root_names_the_way_to_repeat_instead_of_reinstalling(
    tmp_path: Path,
) -> None:
    """🔴 Обновление без прав не подменяется установкой с нуля через sudo-однострок.

    Односторок потерял бы и версию, от которой идём, и заставку обновления: человек
    просил обновить, а получил бы полную переустановку. Сеть при этом не трогается вовсе
    - отказ стоит до всякого запроса.
    """
    hits: dict[str, int] = {}
    port = _stub_github(tag="v9.9.9", tarball=None, sha256_body=None, hits=hits)
    env = {"TORRCAST_UPGRADE_FROM": "1.0.0", "TORRCAST_NO_ROOT": ""}
    done = _run_bootstrap(tmp_path, port, env)

    assert done.returncode == 1
    assert "root is required: sudo cast --upgrade" in done.stderr
    assert hits == {}, "за тегом сходили, хотя прав на установку нет"


def test_the_upgrade_has_no_second_download_body_of_its_own() -> None:
    """🔴 Загрузчик один, входов два. Второе тело закачки разъехалось бы с первым.

    Сторож смотрит не на слова, а на места, где второе тело могло бы завестись: отдельный
    upgrade.sh в дереве и знание о выпусках внутри пакета. Питон обязан знать про
    обновление ровно одно - какой файл запустить.
    """
    assert not (REPO / "upgrade.sh").exists(), "заведён второй вход со своим телом"
    knowing = []
    for module in (REPO / "torrcast").rglob("*.py"):
        text = module.read_text(encoding="utf-8")
        if "releases/latest" in text or "sha256sum" in text or "tarfile" in text:
            knowing.append(str(module.relative_to(REPO)))
    assert knowing == []


@pytest.mark.machine
def test_a_language_nobody_knows_is_refused_by_a_code_that_means_only_that(
    tmp_path: Path,
) -> None:
    """🔴 TC-887. Двойка занята, и занята штатным исходом.

    Установщик отдаёт 2, когда каталог индексеров вышел беднее полного (EXIT_CATALOG_CUT),
    и `cast --upgrade` считает такой исход успехом - иначе всякий, кто ставил продукт с
    неполным каталогом, читал бы «обновление не прошло» после успешного обновления.
    Загрузчик стоит на том же тракте, и его собственный отказ обязан звучать другим
    числом: иначе непонятое значение TORRCAST_LANGUAGE доехало бы до человека словом
    «обновлено», хотя не тронуто ничего. Значение читается из install.sh формой.
    """
    cut = re.findall(r"^EXIT_CATALOG_CUT=([0-9]+)$", INSTALLER, re.M)
    assert len(cut) == 1, "EXIT_CATALOG_CUT в install.sh нет или он не один"

    done = _run_bootstrap(tmp_path, 1, {"TORRCAST_LANGUAGE": "de"}, sealed=True)

    assert "TORRCAST_LANGUAGE must be en or ru" in done.stderr
    assert done.returncode != int(cut[0]), "отказ разбора звучит кодом урезанного каталога"
    assert done.returncode == 1, done.returncode
