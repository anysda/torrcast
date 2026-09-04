"""Ограждения критического пути установки.

Сам install.sh меняет систему, поэтому тест проверяет его контракт как текст:
добавление индексеров не уходит в фон, а отказ Prowlarr остаётся виден.
"""

import ipaddress
import json
import os
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from itertools import pairwise
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

REPO = Path(__file__).parents[1]
SCRIPT = (REPO / "install.sh").read_text(encoding="utf-8")
#: Адреса, поднятые на петле по умолчанию и в Linux, и в macOS. Больше на `lo0`
#: у macOS нет ничего: `in_pcbbind` требует точного совпадения с адресом
#: интерфейса, маску он не смотрит, и остальной 127/8 там просто не завести.
LOOPBACK_EVERYWHERE = ("127.0.0.1", "::1")


def _body(name: str) -> str:
    return SCRIPT.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _install_indexers() -> str:
    return SCRIPT.split("install_indexers() {", 1)[1].split("# --- 6.", 1)[0]


def test_every_subscripted_shell_name_is_initialized() -> None:
    """An orphaned array name becomes arithmetic under ``set -u``.

    ``${UNKNOWN[key]:-}`` looks guarded, but Bash evaluates ``key`` as an
    arithmetic subscript before applying ``:-``.  Keep every subscripted name
    tied to an assignment somewhere in the installer; ``BASH_SOURCE`` is the
    one array Bash itself initializes.
    """
    subscripted = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\[[^]]+\]", SCRIPT))
    code = "\n".join(line for line in SCRIPT.splitlines() if not re.match(r"^\s*#", line))
    initialized = set(
        re.findall(
            r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)(?:\[[^]]*\])?=",
            code,
        )
    )

    assert subscripted - initialized - {"BASH_SOURCE"} == set()


def test_commented_array_declarations_do_not_satisfy_the_initialization_guard() -> None:
    code = "# LOST=()\nprintf '%s' \"${LOST[item]:-}\"\n"
    subscripted = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\[[^]]+\]", code))
    uncommented = "\n".join(line for line in code.splitlines() if not re.match(r"^\s*#", line))
    initialized = set(
        re.findall(
            r"(?<![A-Za-z0-9_])([A-Za-z_][A-Za-z0-9_]*)(?:\[[^]]*\])?=",
            uncommented,
        )
    )
    assert subscripted - initialized == {"LOST"}


def test_indexers_are_added_one_at_a_time() -> None:
    body = _install_indexers()
    assert "INDEXER_ADD_GAP" in body
    assert 'sleep "$INDEXER_ADD_GAP"' in body
    assert "pids+=(" not in body


def test_an_add_failure_names_the_prowlarr_response_and_continues() -> None:
    """🔴 TC-692. Отказ добавления - отказ КАТАЛОГА, а не «не блокер»: строка обязана
    назвать причину из тела ответа Prowlarr и сказать про урезанный каталог, а
    отказавшие индексеры переспрашиваются догревом, пока окно канала не откроется."""
    body = _install_indexers()
    assert "Prowlarr ответил HTTP $status" in body
    assert " - не блокер" not in body
    assert "каталог неполный" in body
    assert 'retry_add_indexers "$key"' in body


def test_anilibria_is_a_regular_indexer_with_a_shim_route() -> None:
    assert '"anilibria|http://localhost:9697/"' in SCRIPT
    assert "'anilibria.top|/api/v1/app/search/releases?query=Kaiba||" in SCRIPT
    assert '"$REPO_DIR/scripts/anilibria.yml"' in SCRIPT
    assert (REPO / "scripts" / "anilibria.yml").is_file()


def test_jacred_is_a_regular_indexer_with_a_shim_route() -> None:
    assert '"jacred|http://127.0.0.1:9698/"' in SCRIPT
    assert "'api.jacred.su|/api/search?query=matrix&sort=sid&limit=100||" in SCRIPT
    assert '"$REPO_DIR/scripts/jacred.yml"' in SCRIPT
    assert (REPO / "scripts" / "jacred.yml").is_file()


def test_the_two_local_indexers_do_not_share_one_prowlarr_queue() -> None:
    """Prowlarr paces its asks per host and ignores the port: one host means one queue.

    Measured on the live stand, an adapter whose call arrives in 0.01 s waited 2.01 s when
    its neighbour had just been asked under the same host.  The key of that queue is the
    host string as it is written, not the address behind it, so two spellings of the very
    same loopback are two queues - and one spelling, however spelled, is one.
    """
    rows = dict(re.findall(r'"(anilibria|jacred)\|http://([^:/]+):\d+/"', SCRIPT))
    assert set(rows) == {"anilibria", "jacred"}, f"both local indexers are registered: {rows}"
    assert rows["anilibria"] != rows["jacred"], (
        f"both local indexers sit on {rows['anilibria']} and take turns in one Prowlarr queue"
    )


def test_each_local_indexer_listens_where_it_is_registered() -> None:
    """A half-done move is worse than none: the address is written down in three places.

    One of the two is registered under a name, so the string Prowlarr is given is not the
    string the adapter binds.  What has to hold is that the name resolves to the loopback
    the adapter listens on: knock where nobody answers, and the catalogue is gone.
    """
    for name, port in (("anilibria", 9697), ("jacred", 9698)):
        (host,) = re.findall(rf'"{name}\|http://([^:/]+):{port}/"', SCRIPT)
        served = (REPO / "scripts" / f"{name}-indexer.py").read_text()
        listed = (REPO / "scripts" / f"{name}.yml").read_text()
        (bound,) = re.findall(r'^HOST = "(.+)"$', served, re.M)
        reached = {where[0] for *_, where in socket.getaddrinfo(host, port, socket.AF_INET)}
        assert bound in reached, f"{name} is called at {host} ({reached}) but listens on {bound}"
        assert f"http://{host}:{port}/" in listed, f"{name}.yml points somewhere else than {host}"


def test_the_local_indexers_bind_only_what_macos_keeps_on_lo0() -> None:
    """🔴 Адрес из 127/8, кроме первого, на маке не поднимается - и каталог пропадает молча.

    На Linux `bind` спрашивает таблицу маршрутов, куда ядро кладёт всю сеть 127/8, поэтому
    `127.0.0.2` там встаёт. На macOS `in_pcbbind` требует ТОЧНОГО совпадения с адресом
    интерфейса (`ifa_ifwithaddr`) и маску не смотрит вовсе, а на `lo0` по умолчанию поднят
    один `127.0.0.1`: `bind` отдал бы `EADDRNOTAVAIL`, адаптер не встал бы, `wait_http`
    истёк бы предупреждением - и установка сказала бы «готово», потеряв каталог целиком.
    Алиас `ifconfig lo0 alias` перезагрузку не переживает, шагом установки это не лечится.
    """
    for name in ("anilibria", "jacred"):
        served = (REPO / "scripts" / f"{name}-indexer.py").read_text()
        (bound,) = re.findall(r'^HOST = "(.+)"$', served, re.M)
        loopback = ipaddress.ip_address(bound).is_loopback
        assert loopback, f"{name} listens on {bound}, sitting off the loopback"
        assert bound in LOOPBACK_EVERYWHERE, (
            f"{name} binds {bound}, and macOS keeps only {LOOPBACK_EVERYWHERE} on lo0: "
            "bind() answers EADDRNOTAVAIL there and the whole catalogue vanishes in silence"
        )


def test_install_removes_its_login_notice_without_a_motd_phase() -> None:
    phases = SCRIPT.split('PHASES="', 1)[1].split('"', 1)[0]
    assert "cleanup_login_notice() {" in SCRIPT
    cleanup = SCRIPT.split("cleanup_login_notice() {", 1)[1].split("\n}", 1)[0]

    assert "motd" not in phases
    assert 'rm -f "$motd_d/00-torrcast"' in cleanup
    assert "cast status | stop | doctor" in cleanup
    assert "cleanup_login_notice" in SCRIPT.split("main() {", 1)[1]


def test_imdb_files_follow_the_state_directory() -> None:
    assert (
        'IMDB_RATINGS_PATH="${TORRCAST_IMDB_RATINGS_PATH:-$STATE_DIR/imdb-ratings.tsv}"' in SCRIPT
    )
    assert 'IMDB_NAMES_PATH="${TORRCAST_IMDB_NAMES_PATH:-$STATE_DIR/imdb-ru-names.tsv}"' in SCRIPT


@pytest.mark.machine
def test_receiver_setup_never_reads_an_answer(tmp_path: Path) -> None:
    """Несколько приёмников не превращают установку в меню.

    В stdin нарочно лежит ответ: вызванный `cast` не должен его увидеть.
    """
    box = tmp_path / "receiver"
    bindir = box / "bin"
    configdir = box / "etc"
    bindir.mkdir(parents=True)
    configdir.mkdir()
    (configdir / "config.json").write_text('{"tv": null}\n', encoding="utf-8")
    cast = bindir / "cast"
    cast.write_text(
        "#!/bin/sh\n"
        'if IFS= read -r answer; then echo "asked:$answer"; exit 9; fi\n'
        "printf '  1. Гостиная - 192.0.2.10\\n  2. Спальня - 192.0.2.11\\n'\n"
        "exit 1\n",
        encoding="utf-8",
    )
    cast.chmod(0o755)
    env = {
        **os.environ,
        "TORRCAST_PHASES": "receiver",
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_NO_SYSTEMD": "1",
        "TORRCAST_PREFIX": str(box),
        "TORRCAST_CONFIG_DIR": str(configdir),
        "TORRCAST_STATE_DIR": str(box / "var"),
        "TORRCAST_BIN_DIR": str(bindir),
        "TORRCAST_MOTD": str(box / "motd"),
        "TORRCAST_MOTD_D": str(box / "motd.d"),
    }
    done = subprocess.run(
        [str(REPO / "install.sh")],
        input="1\n",
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    printed = done.stdout + done.stderr
    assert done.returncode == 0, printed
    assert "asked:" not in printed
    assert "Гостиная - 192.0.2.10" in printed
    assert "Спальня - 192.0.2.11" in printed
    assert "cast --tv <ip>" in printed and "cast --tv to choose by number" in printed


def test_name_map_intermediates_stay_beside_the_result() -> None:
    body = SCRIPT.split("setup_names() {", 1)[1].split("\n}", 1)[0]
    assert 'local names="$IMDB_NAMES_PATH.akas.part"' in body
    assert 'local basics="$IMDB_NAMES_PATH.basics.part"' in body
    assert "mktemp" not in body


def _warm_budget_probe() -> str:
    """Ровно тот питон, который установщик выполняет, - вынутый из его же текста."""
    body = _body("warm_budget")
    # Сам сниппет одинарных кавычек не содержит, поэтому его границы - первая пара.
    return body.split("'", 1)[1].split("'", 1)[0]


def test_the_installer_asks_the_package_for_the_warm_budget() -> None:
    """🔴 TC-621. Проба обязана быть импортом: он идёт за именем и переживает переезд."""
    body = _body("warm_budget")
    assert "import ast" not in body
    assert "torrcast/warm.py" not in body
    assert "from torrcast" in body and "import WARM_BUDGET" in body


@pytest.mark.machine
def test_the_warm_budget_probe_still_resolves_after_the_split() -> None:
    """🔴 TC-621. Мера меряет ЦЕЛЬ: гоняем команду установщика и ждём то самое число.

    Разбор файла по пути молчал, когда разрез увёз константу. Этот тест краснеет в
    гейте на СЛЕДУЮЩЕМ же переезде, а не на живой установке у человека.
    """
    from torrcast.domain.warm_settings import WARM_BUDGET

    env = {**os.environ, "PYTHONPATH": str(REPO)}
    done = subprocess.run(
        [sys.executable, "-c", _warm_budget_probe()],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert int(done.stdout.strip()) == WARM_BUDGET


def test_a_failed_warm_budget_probe_reaches_the_installer_as_a_failure() -> None:
    """🔴 TC-621. Тонувший код возврата и был причиной «не найден» при RC=0.

    Фазу заводит `job_start`, а там тело идёт под ``|| rc=$?`` - контекст, который
    гасит errexit на всю глубину вызова. Значит провал несём наверх руками.
    """
    assert 'budget="$(warm_budget)" || return 1' in _body("ts_cache_disk")
    assert 'disk="$(ts_cache_disk)" || return 1' in _body("ts_cache_place")
    assert 'place="$(ts_cache_place)" || die' in _body("install_torrserver")


@pytest.mark.machine
def test_the_warming_already_on_disk_is_not_reserved_twice(tmp_path: Path) -> None:
    """🔴 TC-725. Занятое прогревом уже вычтено из свободного места раздела.

    Замер стенда, ради которого правило написано: раздел 52.7 ГБ, прогретого 15.3 ГБ,
    свободно 23.1 ГБ. Резерв поверх свободного просил бы 33.2 ГБ - кэшу на диске
    выходил ноль, он уезжал в память и стоил службе 5.9 ГиБ при 8 ГБ у машины вместо
    104 МиБ на диске.
    """
    from torrcast.domain.warm_settings import WARM_BUDGET

    free, warmed = 23_065_513_984, 15_315_748_102
    floor = 3 * 1024**3
    script = f"""
set -eu
REPO_DIR={shlex.quote(str(REPO))}
eval "$(sed -n '/^warm_budget() {{$/,/^}}$/p;/^warm_dir() {{$/,/^}}$/p;\
/^warm_used() {{$/,/^}}$/p;/^ts_cache_disk() {{$/,/^}}$/p' {shlex.quote(str(REPO / "install.sh"))})"
pick_python() {{ PYTHON={shlex.quote(sys.executable)}; }}
loud() {{ printf '%s\\n' "$*" >&2; }}
TS_DISK_FLOOR={floor}
TS_CACHE_MAX={8 * 1024**3}
TS_CACHE_DIR={shlex.quote(str(tmp_path))}
TORRCAST_WARM={shlex.quote(str(tmp_path / "warm"))}
disk_free() {{ printf '%s' {free}; }}
ts_cache_disk
"""
    warm = tmp_path / "warm" / "показ"
    warm.mkdir(parents=True)
    with (warm / "v0.ts").open("wb") as piece:
        piece.truncate(warmed)

    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stderr
    assert int(done.stdout) == free - (WARM_BUDGET - warmed) - floor, done.stdout
    assert int(done.stdout) > 3 * 1024**3, "кэшу на диске не осталось места - он уедет в память"


@pytest.mark.machine
def test_the_warming_is_weighed_the_same_on_a_machine_whose_awk_rounds(tmp_path: Path) -> None:
    """🔴 Вес прогретого не отдан awk: у части машин он врёт, и врёт молча.

    Замер двух машин с одним и тем же прогретым: mawk 1.3.4 20200120 печатает сумму
    6413961908 как «6,41396e+09» - экспоненциальной записью и с запятой из локали, -
    а mawk 1.3.4 20250131 отдаёт целое. Нечисло проверка `warm_used` читает как ноль,
    и весь бюджет прогрева резервируется поверх уже занятого: та самая ошибка, ради
    которой функция написана, только теперь молча и не везде.

    Здесь на PATH кладётся awk, который ведёт себя как первый из двух. Правило обязано
    отдать точный вес - значит спрашивать awk оно не вправе вовсе.
    """
    warmed = 6_413_961_908
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "awk").write_text("#!/bin/sh\ncat >/dev/null\nprintf '6,41396e+09\\n'\n")
    (stub / "awk").chmod(0o755)
    script = f"""
set -eu
PATH={shlex.quote(str(stub))}:$PATH
REPO_DIR={shlex.quote(str(REPO))}
eval "$(sed -n '/^warm_dir() {{$/,/^}}$/p;/^warm_used() {{$/,/^}}$/p' \
    {shlex.quote(str(REPO / "install.sh"))})"
pick_python() {{ PYTHON={shlex.quote(sys.executable)}; }}
loud() {{ printf '%s\\n' "$*" >&2; }}
TORRCAST_WARM={shlex.quote(str(tmp_path / "warm"))}
warm_used
"""
    warm = tmp_path / "warm" / "показ"
    warm.mkdir(parents=True)
    with (warm / "v0.ts").open("wb") as piece:
        piece.truncate(warmed)

    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stderr
    assert done.stdout == str(warmed), f"вес прогретого сосчитан как {done.stdout!r}"


def test_the_catalog_stands_on_roles_and_a_role_may_have_two_carriers() -> None:
    """🔴 TC-705. Каталог держится не на именах, а на ролях: русские раздачи несут два
    источника, и любой из них закрывает роль. Судить по именам - значит звать урезанным
    полный каталог и молчать про источник, которого никто не спрашивал."""
    roles = SCRIPT.split("CATALOG_ROLES=(", 1)[1].split(")", 1)[0]
    assert "western releases and anime^западные релизы и аниме|$KEY_INDEXER" in roles
    assert "Russian releases and voiceovers^русские раздачи и озвучки|rutor jacred" in roles
    # На глазах добавляют ПЕРВОГО носителя роли, а не всякого: запасной ждёт своего часа.
    assert "lead_indexer" in _body("late_indexer")
    assert 'LATE_INDEXERS=("yts" "jacred")' in SCRIPT


def test_the_catalog_gate_asks_the_search_not_the_list() -> None:
    """🔴 TC-692. «Числится» и «отвечает» - разные утверждения: rutor стоял в списке
    включённым и не отдавал ничего, а установка объявляла успех. Гейт спрашивает поиск."""
    gate = _body("catalog_gate")
    assert "indexer_yield" in gate and "/api/v1/search" in _body("indexer_yield")
    assert "не завёлся" in gate and "не отдал ничего" in gate
    assert 'CATALOG_CUT_EN="$cut_en"' in gate
    assert 'CATALOG_CUT_RU="$cut_ru"' in gate
    # Носители ролей щупаются на глазах, поэтому в догрев (`check_indexers`) не уезжают.
    assert 'core_indexer "$def" || rest+=(' in _install_indexers()


def test_the_gate_asks_the_second_carrier_only_when_the_role_stays_unanswered() -> None:
    """🔴 TC-705. Цена вопроса названа: одно добавление стоит до сотни секунд, потому что
    Prowlarr щупает источник сам. Поэтому запасного носителя гейт заводит не всегда, а
    только когда роль осталась без ответа - там эти секунды покупают правду о каталоге.
    На здоровом пути его добавление остаётся в догреве, и установка не ждёт ни секунды.
    """
    gate = _body("catalog_gate")
    # Роль закрыта - остальные её носители не спрашиваются вовсе: обращение к трекеру
    # стоит суток его ступени бана.
    assert '[ -z "$covered" ] || break' in gate
    assert 'if [ -z "$id" ] && [ -n "$(catalog_standby_get "$def")" ]; then' in gate
    # Заведённый гейтом не заводится ещё раз догревом.
    assert 'CATALOG_PROMOTED+=("$iname")' in _body("promote_standby")
    assert 'catalog_promoted "$iname" && continue' in _install_indexers()


@pytest.mark.machine
def test_unsupported_os_refuses_before_any_installation_work(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    uname = fake_bin / "uname"
    uname.write_text("#!/bin/sh\nprintf 'FreeBSD\\n'\n", encoding="utf-8")
    uname.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{fake_bin}:{env['PATH']}"

    run = subprocess.run(
        ["bash", str(REPO / "install.sh"), "-ru"],
        text=True,
        capture_output=True,
        env=env,
        timeout=5,
        check=False,
    )

    assert run.returncode == 2
    assert run.stdout == ""
    assert run.stderr == "ошибка: нужен Debian/Ubuntu или macOS\n"


def test_macos_reaches_packages_without_bash4_or_linux_locale_work() -> None:
    locale = _body("setup_locale")
    packages = _body("install_packages")

    assert locale.index('[ "${OS_FAMILY:-linux}" = macos ]') < locale.index(
        'locale_build "$LOCALE"'
    )
    assert "локалью управляет macOS; системные файлы менять не нужно" in locale
    assert packages.index('[ "${OS_FAMILY:-linux}" = macos ]') < packages.index(
        "apt_candidate_version"
    )
    assert 'brew_as_invoker install "${BREW_PACKAGES[@]}"' in packages
    assert '"$SUDO" -H -u "$SUDO_USER" "$brew_bin" "$@"' in SCRIPT
    assert "SUDO_USER пуст" in SCRIPT
    # Совместимость со штатным bash мака мерится целиком в tests/test_installold.py:
    # там разбор ВСЕГО файла на конструкции 4+/5+ и живой прогон заставки под настоящим
    # 3.2.57. Список из двух имён здесь был снимком, а не правилом, и молчал бы на
    # третьей конструкции. Мака же касается только номер канала: автономер {fd} - это
    # 4.1, поэтому на старом интерпретаторе девятка называется руками.
    assert 'exec 9<"$UI_CHANNEL"' in SCRIPT


def test_release_assets_are_selected_by_os_and_architecture() -> None:
    torrserver = _body("torrserver_asset_name")
    prowlarr = _body("prowlarr_asset_name")

    assert "linux) os=linux" in torrserver and "macos) os=darwin" in torrserver
    assert "x86_64) arch=amd64" in torrserver
    assert "aarch64|arm64) arch=arm64" in torrserver
    assert "linux) os=linux" in prowlarr and "macos) os=osx" in prowlarr
    assert "x86_64) arch=x64" in prowlarr
    assert "aarch64|arm64) arch=arm64" in prowlarr
    assert "endswith($suffix)" in _body("install_prowlarr_binary")


def test_macos_uses_brew_ffmpeg_and_installs_no_keychain_trust() -> None:
    """The macOS keychain refuses unattended trust, so no trusted root is installed
    there at all; Prowlarr relaxes checks for local addresses only (see
    tests/test_install_launchd.py)."""
    ffmpeg = _body("install_ffmpeg")

    assert ffmpeg.index('[ "${OS_FAMILY:-linux}" = macos ]') < ffmpeg.index("static ffmpeg build")
    assert "brew_as_invoker install ffmpeg" in ffmpeg
    # brew's prefix is on nobody's default PATH; link the tools where login shells,
    # sudo and launchd jobs all see them.
    assert 'ln -sfn "$ff" "$BIN_DIR/ffmpeg"' in ffmpeg
    assert 'ln -sfn "$fp" "$BIN_DIR/ffprobe"' in ffmpeg
    assert "security add-trusted-cert" not in SCRIPT
    assert "security delete-certificate" not in SCRIPT
    assert "remove_shim_trust" not in SCRIPT
    assert "update-ca-certificates --fresh" in _body("retire_old_shim")


def test_brew_as_invoker_installs_homebrew_instead_of_asking_a_human() -> None:
    """Мак без Homebrew - не «установите его руками», а установка самой установкой.

    Шов один (brew_as_invoker), и установка живёт в нём: фазы зовут выборочно
    (TORRCAST_PHASES), отдельный шаг фазы можно было бы пропустить, а мимо шва не
    пройти. Честные отказы на бессмысленном запуске остаются."""
    seam = _body("brew_as_invoker")
    installer = _body("install_homebrew")

    assert "install_homebrew" in seam
    assert "install it as $SUDO_USER" not in seam
    # Отказы, которые законны: пустой SUDO_USER и несуществующий позвавший.
    assert "SUDO_USER пуст" in seam
    assert "не существует" in seam
    # Под root Homebrew не работает вовсе - ставит позвавший sudo, и строго безголово:
    # без NONINTERACTIVE=1 установщик ждёт нажатия RETURN и вешает установку насмерть.
    assert '"$SUDO" -H -u "$SUDO_USER" env NONINTERACTIVE=1 /bin/bash "$script"' in installer
    # mktemp даёт 0600 владельцу-root, а читает файл позвавший sudo (живой прогон на
    # маке: Permission denied). Файл обязан стать читаемым до передачи.
    assert 'chmod 0644 "$script"' in installer
    # Чужой пакетный менеджер на машине человека ставится вслух, а не молча:
    # `loud` уходит в ленту под рамкой заставки и не тонет в журнале.
    assert "https://brew.sh" in installer
    assert "loud" in installer


@pytest.mark.machine
def test_a_mac_without_homebrew_gets_it_from_the_installer_itself(tmp_path: Path) -> None:
    """Фаза packages на маке без Homebrew ставит его сама, позвавшим sudo, безголово.

    Мера - поведение шва, а не его текст: подставные uname (Darwin), sudo (пишет
    вызов и исполняет) и установщик Homebrew (кладёт подставной brew). Второй прогон
    обязан пройти мимо установки: brew уже есть, ставить заново нельзя.
    """
    box = tmp_path / "box"
    bindir = box / "bin"
    bindir.mkdir(parents=True)
    uname = bindir / "uname"
    uname.write_text(
        "#!/bin/sh\ncase \"$1\" in -m) printf 'arm64\\n';; *) printf 'Darwin\\n';; esac\n",
        encoding="utf-8",
    )
    uname.chmod(0o755)
    sudo_log = box / "sudo.log"
    sudo = bindir / "sudo"
    sudo.write_text(
        "#!/bin/sh\n"
        f'printf "%s\\n" "$*" >> "{sudo_log}"\n'
        'while :; do case "${1:-}" in -H) shift ;; -u) shift 2 ;; *) break ;; esac; done\n'
        'exec "$@"\n',
        encoding="utf-8",
    )
    sudo.chmod(0o755)
    brew_log = box / "brew.log"
    # Подставной установщик Homebrew: без NONINTERACTIVE=1 отказывает, как настоящий,
    # который ждал бы RETURN; с ним - кладёт подставной brew.
    installer = box / "homebrew-install.sh"
    installer.write_text(
        "#!/bin/bash\n"
        'if [ "${NONINTERACTIVE:-}" != 1 ]; then\n'
        '    printf "Homebrew installer would wait for RETURN here\\n" >&2\n'
        "    exit 1\n"
        "fi\n"
        f"cat > \"{bindir}/brew\" <<'BREW'\n"
        "#!/bin/bash\n"
        f'printf "%s\\n" "$*" >> "{brew_log}"\n'
        'if [ "$1" = "--prefix" ]; then printf "%s\\n" "' + str(box / "prefix") + '"; fi\n'
        "BREW\n"
        f'chmod +x "{bindir}/brew"\n'
        'printf "fake homebrew installed\\n" >&2\n',
        encoding="utf-8",
    )
    user = subprocess.run(["id", "-un"], capture_output=True, text=True, check=True).stdout.strip()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "SUDO_USER": user,
        "TORRCAST_SUDO": str(sudo),
        "TORRCAST_HOMEBREW_URL": f"file://{installer}",
        "TORRCAST_PHASES": "packages",
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_NO_SYSTEMD": "1",
        "TORRCAST_PREFIX": str(box / "opt"),
        "TORRCAST_CONFIG_DIR": str(box / "etc"),
        "TORRCAST_STATE_DIR": str(box / "var"),
        "TORRCAST_BIN_DIR": str(box / "usr-bin"),
        "TORRCAST_MOTD": str(box / "motd"),
        "TORRCAST_MOTD_D": str(box / "motd.d"),
    }

    first = subprocess.run(
        [str(REPO / "install.sh"), "-ru"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    shown = first.stdout + first.stderr
    assert first.returncode == 0, shown
    assert "ставлю его под" in shown, f"установка Homebrew прошла молча: {shown!r}"
    calls = sudo_log.read_text(encoding="utf-8").splitlines()
    setup = [line for line in calls if "homebrew-install" in line]
    assert len(setup) == 1, f"установщик Homebrew позван не ровно один раз: {calls!r}"
    assert f"-u {user}" in setup[0], f"Homebrew ставит не позвавший sudo: {setup[0]!r}"
    assert "NONINTERACTIVE=1" in setup[0], f"установщику дали повеситься на RETURN: {setup[0]!r}"
    assert "install jq python@3.11 ffmpeg" in brew_log.read_text(encoding="utf-8")

    # Второй прогон по уже поставленному: brew на месте, ставить заново нельзя.
    second = subprocess.run(
        [str(REPO / "install.sh"), "-ru"],
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
        check=False,
    )

    shown = second.stdout + second.stderr
    assert second.returncode == 0, shown
    assert "ставлю его под" not in shown, f"Homebrew переставляется поверх живого: {shown!r}"
    calls = sudo_log.read_text(encoding="utf-8").splitlines()
    assert len([line for line in calls if "homebrew-install" in line]) == 1, (
        f"установщик Homebrew позван повторно: {calls!r}"
    )


def test_case_arms_inside_command_substitutions_keep_their_balancing_paren() -> None:
    """Рукав case внутри $(...) пишется со скобкой: `(шаблон)`, не `шаблон)`.

    Стоковый bash 3.2 мака ищет конец подстановки простым счётом скобок: непарная `)`
    рукава обрезает её, и установка умирает «command substitution: syntax error»
    посреди фазы (куплено живым прогоном на bash 3.2.57 в warm_used). Страхуем весь
    install.sh, а не одно найденное место.

    Мера зеркалит сам дефект: считаем скобки так же наивно, как bash 3.2, - и смотрим
    на ТЕРМИНАТОР подстановки. Здоровая подстановка кончается своей скобкой; если её
    обрезал рукав case (тело при этом усечено, по esac ориентироваться нельзя),
    последним словом тела стоит «шаблон» рукава сразу после `in` или `;;`.
    """
    offenders: list[str] = []
    i = 0
    while True:
        start = SCRIPT.find("$(", i)
        if start < 0:
            break
        depth, k = 1, start + 2
        while k < len(SCRIPT) and depth:
            if SCRIPT[k] == "(":
                depth += 1
            elif SCRIPT[k] == ")":
                depth -= 1
            k += 1
        body = SCRIPT[start + 2 : k - 1]
        i = k
        if "case " not in body:
            continue
        tail = re.search(r"(\S[^()\s]*)$", body)
        if tail and re.search(r"(?:\bin|;;)\s*$", body[: tail.start(1)]):
            offenders.append(tail.group(1))

    assert offenders == [], f"рукавы case внутри $() без парной скобки: {offenders!r}"


def test_a_cut_catalog_is_not_a_successful_install() -> None:
    """🔴 TC-692. Пустой каталог под видом успеха - неправда и для человека, и для
    автоматики: последнее слово установки называет урез и возвращает ненулевой код."""
    main = _body("main")
    assert 'if [ -n "$CATALOG_CUT_EN" ]; then' in main
    assert 'exit "$EXIT_CATALOG_CUT"' in main
    assert "EXIT_CATALOG_CUT=2" in SCRIPT


def test_the_indexer_texts_match_what_the_installer_actually_does() -> None:
    """🔴 TC-697. Три текста рядом врали: догрев звал опорным одного (их два), а срок
    переспроса обещал «до двух минут» при двенадцати кругах по пять минут.

    Две минуты - честный потолок ровно для того, кого добавляют ОДИН раз (замер: 100 с
    на yts), а срок переспроса теперь не обещается словами, а считается из тех же двух
    ручек, которыми он и задан, - соврать он больше не может.
    """
    assert "кроме опорных" in SCRIPT
    assert "кроме ключевого" not in SCRIPT and "Ключевой проверяется" not in SCRIPT
    body = _install_indexers()
    assert '"indexer $names (may take up to two minutes to add)"' in body
    assert '"индексер $names (добавляется до двух минут)" add_indexers' in body
    assert "span=$(( more * INDEXER_RETRY_EVERY / 60 ))" in body
    assert "это до $span мин" in body


#: Заглушки живых Prowlarr, поднятые тестом: гасить их надо ПОСЛЕ замера, а не в
#: момент выхода установки - догрев догревает уже после «готово», и рано закрытый
#: сервер превращал бы его обращения в отказы соединения (TC-697).
_STUBS: list[ThreadingHTTPServer] = []


@pytest.fixture(autouse=True)
def _stop_stub_prowlarrs() -> Iterator[None]:
    yield
    for server in _STUBS:
        server.shutdown()
    _STUBS.clear()


#: Схема Prowlarr для заглушки: только то, что установка из неё берёт.
_STUB_SCHEMA = [
    {
        "definitionName": name,
        "name": human,
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "priority": 25,
        "protocol": "torrent",
        "fields": [{"name": "baseUrl", "value": ""}, {"name": "apiurl", "value": ""}],
    }
    for name, human in (
        ("Knaben", "Knaben"),
        ("rutor", "RuTor"),
        ("nyaasi", "Nyaa.si"),
        ("anilibria", "AniLibria"),
        ("jacred", "JacRed"),
        ("yts", "YTS"),
    )
]


def _stub_prowlarr(
    fail: frozenset[str], silent: frozenset[str]
) -> tuple[int, dict[str, list[float]]]:
    """Заглушка Prowlarr: отвечает как живой, но кого щупать успешно - решаем мы.

    Живой Prowlarr на молчащий трекер отвечает 400 с телом про 502, а забаненный
    индексер у него числится включённым и отдаёт пустой поиск - обе беды здесь и
    инсценируются, потому что от канала их не дождёшься по заказу. Каждый POST на
    добавление записывается с моментом: число обращений к индексеру и паузы между
    ними - то, ради чего замер (TC-697: дубль пробы в первую минуту).
    """
    added: list[dict[str, object]] = []
    posts: dict[str, list[float]] = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:  # тишина в отчёте теста
            return

        def _send(self, code: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            path = urlparse(self.path)
            if path.path == "/api/v1/indexer/schema":
                return self._send(200, _STUB_SCHEMA)
            if path.path == "/api/v1/indexer":
                return self._send(200, added)
            if path.path == "/api/v1/indexerstatus":
                return self._send(200, [])
            if path.path == "/api/v1/search":
                ids = parse_qs(path.query).get("indexerIds", [""])[0]
                name = next((str(i["name"]) for i in added if str(i["id"]) == ids), "?")
                hits = 0 if name in silent else 3
                return self._send(200, [{"title": f"{name} {n}"} for n in range(hits)])
            return self._send(404, {"message": "нет такого"})

        def do_POST(self) -> None:
            path = urlparse(self.path)
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            if path.path == "/api/v1/indexer/test":
                return self._send(200, {})
            if path.path != "/api/v1/indexer":
                return self._send(404, {"message": "нет такого"})
            body = json.loads(raw or b"{}")
            posts.setdefault(str(body.get("name")), []).append(time.monotonic())
            if body.get("name") in fail:
                return self._send(400, [{"errorMessage": "Unable to connect to indexer"}])
            body["id"] = len(added) + 1
            added.append(body)
            return self._send(201, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    _STUBS.append(server)
    return server.server_port, posts


def _late_settled(box: Path, timeout: float = 30.0) -> str:
    """Дождаться, пока догрев доедет: замер идёт по фоновым заходам, а установка
    отчитывается раньше них - без этой паузы замеряли бы половину правды."""
    log = box / "late.log"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if log.exists():
            text = log.read_text(encoding="utf-8")
            # Слова догрева двуязычны, как и весь вывод установки: считаются оба
            # набора, иначе замер зависел бы от языка стенда, а не от догрева.
            began = text.count(" | начал: ") + text.count(" | started: ")
            ended = (
                text.count(" | готово: ")
                + text.count(" | done: ")
                + text.count(" | НЕ вышло ")
                + text.count(" | FAILED ")
            )
            if began and began == ended:
                return text
        time.sleep(0.05)
    raise AssertionError(f"догрев не доработал за {timeout} с: {log}")


def _run_indexers(
    box: Path,
    fail: frozenset[str] = frozenset(),
    silent: frozenset[str] = frozenset(),
    retry_times: str = "1",
    retry_every: str = "1",
) -> tuple[subprocess.CompletedProcess[str], dict[str, list[float]]]:
    """Прогнать фазу индексеров установки против заглушки Prowlarr."""
    port, posts = _stub_prowlarr(fail, silent)
    (box / "prowlarr-data").mkdir(parents=True)
    (box / "prowlarr-data" / "config.xml").write_text("<Config><ApiKey>proba</ApiKey></Config>")
    env = {
        **os.environ,
        "TORRCAST_PHASES": "indexers",
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_NO_SYSTEMD": "1",
        "TORRCAST_PREFIX": str(box),
        "TORRCAST_CONFIG_DIR": str(box / "etc"),
        "TORRCAST_STATE_DIR": str(box / "var"),
        "TORRCAST_LATE_LOG": str(box / "late.log"),
        "TORRCAST_MOTD": str(box / "motd"),
        "TORRCAST_MOTD_D": str(box / "motd.d"),
        "TORRCAST_PL_PORT": str(port),
        "TORRCAST_INDEXER_ADD_GAP": "0",
        "TORRCAST_SEARCH_TIMEOUT": "3",
        "TORRCAST_INDEXER_RETRY_TIMES": retry_times,
        "TORRCAST_INDEXER_RETRY_EVERY": retry_every,
    }
    done = subprocess.run(
        [str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False
    )
    return done, posts


@pytest.mark.machine
def test_a_cut_catalog_comes_out_of_the_installer_as_a_failure(tmp_path: Path) -> None:
    """🔴 TC-692. Мера меряет ЦЕЛЬ: гоняем саму фазу и смотрим её КОД ВОЗВРАТА.

    Симптом карточки: на чистой установке оба опорных источника получали от Prowlarr
    400, установка печатала «не блокер» и объявляла успех - каталог при этом был пуст.
    Проба инсценирует ровно это, и красным обязан быть код возврата, а не только слова.
    """
    box = tmp_path / "оба-отказали"
    done, posts = _run_indexers(box, fail=frozenset({"Knaben", "RuTor", "JacRed"}))
    assert done.returncode == 2, done.stdout + done.stderr
    printed = done.stdout + done.stderr
    assert (
        "catalog is incomplete: western releases and anime - Knaben (not added); "
        "Russian releases and voiceovers - RuTor (not added), JacRed (not added)" in printed
    )
    assert "не блокер" not in printed
    # 🔴 TC-705. Отказавший запасной ждёт свою роль на той же лестнице переспроса, что и
    # отказавший на глазах: без него роль пуста, а отказ в минуту установки - погода.
    assert "failed core indexers Knaben, RuTor, JacRed" in printed
    # И спрошен он ровно раз: отказ на глазах - это уже проба, второй в ту же минуту
    # ничего не меняет, а ступень бана у трекера продлевает (TC-697).
    _late_settled(box)
    assert len(posts["JacRed"]) == 1


@pytest.mark.machine
def test_a_role_no_one_answers_is_a_cut_catalog(tmp_path: Path) -> None:
    """🔴 TC-692/TC-705. Заведён - не значит отвечает: живьём rutor стоял в списке
    включённым и молчал, а прежняя проверка «добавился ли» такую установку объявляла
    успешной. Урез - это роль, у которой смолчали ВСЕ носители, и названы оба."""
    box = tmp_path / "молчат-оба"
    done, posts = _run_indexers(box, silent=frozenset({"RuTor", "JacRed"}))
    assert done.returncode == 2, done.stdout + done.stderr
    assert (
        "catalog is incomplete: Russian releases and voiceovers - "
        "RuTor (added but returned no results), "
        "JacRed (added but returned no results)" in done.stdout + done.stderr
    )
    # 🔴 TC-697. Заведшийся индексер не переспрашивается: «завёлся и молчит» - не
    # повод для второго обращения, его судьбу решает гейт поиском, а не повторным POST.
    _late_settled(box)
    assert len(posts["RuTor"]) == 1 and len(posts["Knaben"]) == 1
    # Запасной спрошен ровно раз: гейт завёл его сам, догрев второй раз не пошёл.
    assert len(posts["JacRed"]) == 1


@pytest.mark.machine
def test_a_dead_lead_source_is_not_a_cut_catalog_when_its_role_has_a_second_carrier(
    tmp_path: Path,
) -> None:
    """🔴 TC-705. Симптом карточки: rutor не завёлся - и установка возвращала 2 со словами
    про урезанный каталог, хотя русские раздачи в нём несёт второй источник, которого она
    не спрашивала вовсе. Мера меряет ЦЕЛЬ: код возврата и печатаемая строка.
    """
    box = tmp_path / "первый-отказал"
    done, posts = _run_indexers(box, fail=frozenset({"RuTor"}))
    printed = done.stdout + done.stderr
    assert done.returncode == 0, printed
    assert "catalog is incomplete:" not in printed
    assert "role 'Russian releases and voiceovers' is unanswered" in printed
    assert "JacRed responds: 3 results" in printed
    # Запасного спросили один раз, и переспроса он не получил: роль он закрыл.
    _late_settled(box)
    assert len(posts["JacRed"]) == 1


@pytest.mark.machine
def test_the_installer_still_succeeds_when_the_core_sources_answer(tmp_path: Path) -> None:
    """🔴 TC-692. Отрицательная проба к гейту: он обязан УМЕТЬ пропускать. Иначе красный
    код возврата ничего не говорит - его отдавала бы любая установка."""
    box = tmp_path / "все-ответили"
    done, posts = _run_indexers(box)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "catalog is incomplete:" not in done.stdout + done.stderr
    assert "Knaben responds: 3 results" in done.stdout
    # 🔴 TC-705. Роль закрыта первым носителем - запасного на глазах не заводят: сотня
    # секунд на его добавление остаётся в догреве, и установка не ждёт ни секунды.
    assert "is unanswered" not in done.stdout + done.stderr
    assert "JacRed responds" not in done.stdout
    # 🔴 TC-697. Счастливый путь: ровно одно обращение на индексер, дублей нет.
    _late_settled(box)
    for name in ("Knaben", "RuTor", "Nyaa.si", "AniLibria", "YTS", "JacRed"):
        assert len(posts[name]) == 1, f"{name}: обращений {len(posts[name])} вместо одного"


@pytest.mark.machine
def test_a_refused_core_source_is_reasked_after_a_full_pause_not_twice_at_once(
    tmp_path: Path,
) -> None:
    """🔴 TC-697. Дубля в первую минуту быть не должно.

    Отказавший на глазах опорный уже получил свою пробу, поэтому переспрос обязан
    начаться с паузы: RETRY_TIMES - это ВСЕ пробы вместе с той, что на глазах, а не
    одни догревы. Замер числом обращений и пауз между ними.
    """
    box = tmp_path / "отказали"
    done, posts = _run_indexers(
        box, fail=frozenset({"Knaben", "RuTor"}), retry_times="3", retry_every="1"
    )
    assert done.returncode == 2, done.stdout + done.stderr
    _late_settled(box)
    for name in ("Knaben", "RuTor"):
        stamps = posts[name]
        assert len(stamps) == 3, f"{name}: проб {len(stamps)} вместо трёх"
        gaps = [later - earlier for earlier, later in pairwise(stamps)]
        assert all(gap >= 0.9 for gap in gaps), f"{name}: паузы между пробами {gaps}"


@pytest.mark.machine
def test_a_refused_narrow_source_is_not_reasked_at_all(tmp_path: Path) -> None:
    """🔴 TC-697. Переспрос - привилегия опорных: узкий спрашивается один раз.

    Переспрос стоит обращений к источнику, а ступень бана у трекера - сутки. За узкий
    платить их нечем: без него каталог не пустеет (+2.1% раздач и ноль запросов, где он
    единственный источник играбельного HD), тогда как без опорных пул пуст у 97 запросов
    из 99. Не завёлся узкий - его заведёт следующий заход установки.
    """
    box = tmp_path / "узкий-отказал"
    done, posts = _run_indexers(
        box, fail=frozenset({"YTS", "Nyaa.si"}), retry_times="3", retry_every="1"
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "this does not make the catalog incomplete" in done.stdout + done.stderr
    _late_settled(box)
    # Узкие приходят обеими дорогами - из фона (yts) и с глаз (Nyaa.si), и обе спрашивают
    # ровно раз; заведшийся узкий не переспрашивается тем более.
    for name in ("YTS", "Nyaa.si", "JacRed"):
        assert len(posts[name]) == 1, f"{name}: обращений {len(posts[name])} вместо одного"


def _shim_knobs() -> list[str]:
    """Ручки шима так, как их получит юнит: значения подставляет и кавычит сам установщик."""
    body = SCRIPT.split("local knobs; knobs=", 1)[1].split('Sockets=torrcast-shim.socket"', 1)[0]
    agent = SCRIPT.split('\nUA="', 1)[1].split('"\n', 1)[0]
    snippet = (
        f"{_funcs('quoted_knobs')}\n"
        f'UA="{agent}"\n'
        "HOSTS_FILE=/etc/hosts\nSHIM_PID=/etc/torrcast-shim/shim.pid\n"
        "SHIM_DIR=/etc/torrcast-shim\npins=api.knaben.org\nROUTE_EVERY=900\n"
        "PROBE_TIMEOUT=25\nPROBE_STALL=5\nPROBE_FLOOR=1024\n"
        f'knobs={body}Sockets=torrcast-shim.socket"\nquoted_knobs "$knobs"\n'
    )
    done = subprocess.run(["bash", "-c", snippet], capture_output=True, text=True, check=True)
    return done.stdout.splitlines()


def test_a_shim_knob_with_a_space_reaches_the_process_whole() -> None:
    """🔴 TC-704. Значение с пробелом внутри доезжает до шима целиком.

    Строку ``Environment=`` systemd делит по пробелам и всё после первого пробела
    считает СЛЕДУЮЩИМ присваиванием. Браузерная подпись пробы состоит из пробелов чуть
    менее чем полностью, и без кавычек она доезжает обрезанной до ``Mozilla/5.0`` -
    молча, потому что служба при этом исправно поднимается, а обрезанной подписью часть
    трекеров отвечает отказом ещё на пробе. Отказ пробы возвращает имя за шим или
    уводит его оттуда - то есть цена молчания тут не косметическая.
    """
    agent = SCRIPT.split('\nUA="', 1)[1].split('"\n', 1)[0]
    assert " " in agent, "подпись без пробелов эту ловушку не ловит"
    env: dict[str, str] = {}
    for line in _shim_knobs():
        if not line.startswith("Environment="):
            continue
        # Ровно то, что делает systemd: режем по пробелам с оглядкой на кавычки.
        for assignment in shlex.split(line.removeprefix("Environment=")):
            name, _, value = assignment.partition("=")
            env[name] = value
    assert env["TORRCAST_PROBE_UA"] == agent


def _quoted_knobs(knobs: str) -> list[str]:
    """Строки секции ``[Service]`` так, как их окавычит общее место установщика."""
    snippet = f'{_funcs("quoted_knobs")}\nquoted_knobs "$1"\n'
    done = subprocess.run(
        ["bash", "-c", snippet, "проба", knobs], capture_output=True, text=True, check=True
    )
    return done.stdout.splitlines()


def test_every_knob_of_a_unit_comes_out_quoted() -> None:
    """🔴 TC-489. Кавычки ручке ставит установщик, а не тот, кто её написал.

    Строку ``Environment=`` systemd делит по пробелам и всё после первого пробела считает
    СЛЕДУЮЩИМ присваиванием: ручка с пробелом внутри доезжает до процесса обрезанной по
    первому пробелу, и увидеть это можно только в окружении живого процесса - служба
    поднимается как ни в чём не бывало. Зовущих у юнитов много, и помнить про кавычки
    каждому нечем, поэтому мера смотрит на общее место: своё оно кавычит, чужие строки
    секции ``[Service]`` не трогает, а уже окавыченное вторыми кавычками не оборачивает.
    """
    knobs = (
        "Environment=TORRCAST_PROBE_UA=Mozilla/5.0 (X11; Linux x86_64) Chrome/122\n"
        'Environment="TORRCAST_HOSTS=/etc/hosts"\n'
        "MemoryMax=268435456"
    )
    lines = _quoted_knobs(knobs)
    assert lines[-1] == "MemoryMax=268435456", "строки не про ручки трогать нечем"
    seen: dict[str, str] = {}
    for line in lines:
        if not line.startswith("Environment="):
            continue
        # Ровно то, что делает systemd: режем по пробелам с оглядкой на кавычки.
        for assignment in shlex.split(line.removeprefix("Environment=")):
            name, _, value = assignment.partition("=")
            seen[name] = value
    assert seen == {
        "TORRCAST_PROBE_UA": "Mozilla/5.0 (X11; Linux x86_64) Chrome/122",
        "TORRCAST_HOSTS": "/etc/hosts",
    }


def _knob_landed(box: Path, knobs: str, timeout: float = 15.0) -> str:
    """Что доехало до процесса, поднятого песочничной веткой ``run_service``.

    Гоняется сама ветка установщика, а подпись читается из окружения запущенного ею
    процесса: только там видно, доехало значение целиком или его срезало по дороге.
    """
    landed, launched = box / "доехало", box / "служба.sh"
    launched.write_text(
        f'#!/bin/sh\nprintf %s "${{TORRCAST_PROBE_UA-нет}}" >{shlex.quote(str(landed))}\n',
        encoding="utf-8",
    )
    snippet = (
        f"{_funcs('quoted_knobs', 'run_service')}\n"
        "skip() { :; }\n"
        # Шаблон складывается в момент вызова: написанный целиком, он лежал бы в строке
        # запуска самой оболочки, и `pgrep -f` нашёл бы по нему её же.
        "proc_mask() { printf 'нет%sтакого' \"$$\"; }\n"
        f"PREFIX={shlex.quote(str(box))}\nTORRCAST_NO_SYSTEMD=1\n"
        f'run_service проба описание {shlex.quote(f"/bin/sh {launched}")} "$1"\n'
    )
    done = subprocess.run(
        ["bash", "-c", snippet, "проба", knobs], capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stdout + done.stderr
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if landed.exists():
            return landed.read_text(encoding="utf-8")
        time.sleep(0.05)
    raise AssertionError(f"процесс не отчитался за {timeout} с: {done.stdout + done.stderr}")


def test_a_shim_knob_with_a_space_reaches_the_process_in_the_sandbox(tmp_path: Path) -> None:
    """🔴 TC-448. Ручка с пробелом доезжает до процесса целиком и в песочнице тоже.

    Кавычки со значения снимает systemd, а в песочнице юнита нет вовсе: службу поднимает
    сам установщик, и разбирает ручки он же. Разбор, не знающий про кавычки, отдаёт
    ``export`` имя, начинающееся с кавычки, - и роняет весь заход установки, потому что
    ``set -e``. Мера смотрит не текст разбора, а окружение поднятого процесса.
    """
    agent = SCRIPT.split('\nUA="', 1)[1].split('"\n', 1)[0]
    assert " " in agent, "подпись без пробелов эту ловушку не ловит"
    assert _knob_landed(tmp_path, "\n".join(_shim_knobs())) == agent


def _funcs(*names: str) -> str:
    """Тела функций установщика, вынутые из его же текста, - чтобы гонять их взаправду."""
    parts = ["set -euo pipefail", """info() { printf '    %s\\n' "$*"; }"""]
    parts += [f"{name}() {{{_body(name)}\n}}" for name in names]
    return "\n".join(parts)


@pytest.mark.machine
def test_a_module_gone_from_the_tree_goes_from_the_installed_package(tmp_path: Path) -> None:
    """🔴 TC-713. В установленном пакете лежит ровно то, что есть в дереве, - ни файлом больше.

    Запускается не дерево, а установленный пакет, и pip убирает за собой только то, что
    сам записал. Файл, о котором его запись не знает (установку оборвали между сносом
    старого и записью нового), не уносит ни повторный запуск, ни ``--force-reinstall``:
    удалённый из дерева модуль остаётся в site-packages и продолжает импортироваться.
    Тест гоняет саму уборку установщика на разложенных каталогах, а не сверяет её текст.
    """
    src, pkg = tmp_path / "tree", tmp_path / "package"
    for root in (src, pkg):
        (root / "adapters").mkdir(parents=True)
        (root / "__init__.py").touch()
        (root / "adapters" / "live.py").touch()
    (pkg / "adapters" / "__pycache__").mkdir()
    (pkg / "adapters" / "__pycache__" / "live.cpython-311.pyc").touch()
    # Следы модулей, которых в дереве уже нет: сам модуль, осиротевший байт-код и
    # подпакет целиком. Пустой каталог тоже след: по нему `import` состоится.
    (pkg / "ghost.py").write_text("GHOST = 1\n", encoding="utf-8")
    (pkg / "adapters" / "__pycache__" / "ghost.cpython-311.pyc").touch()
    (pkg / "dead_pack").mkdir()
    (pkg / "dead_pack" / "__init__.py").touch()

    done = subprocess.run(
        [
            "bash",
            "-c",
            f'{_funcs("stray_files", "prune_torrcast")}\nprune_torrcast "$1" "$2"',
            "bash",
            str(pkg),
            str(src),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr

    left = sorted(item.relative_to(pkg).as_posix() for item in pkg.rglob("*"))
    assert left == [
        "__init__.py",
        "adapters",
        "adapters/__pycache__",
        "adapters/__pycache__/live.cpython-311.pyc",
        "adapters/live.py",
    ], done.stdout


@pytest.mark.machine
def test_a_torn_install_leaves_no_copy_of_the_old_package(tmp_path: Path) -> None:
    """🔴 TC-713. Оборванная установка чинится СЛЕДУЮЩЕЙ, а не копится.

    Снося прежний пакет, pip сперва переименовывает его в ``~...`` и стирает уже после
    успеха. Убитый на этом месте, он оставляет полную копию прежнего кода: сам он её не
    уберёт никогда, только ругается на неё при каждом запуске, и с каждым обрывом таких
    копий становится больше.
    """
    site = tmp_path / "site-packages"
    (site / "~orcast" / "adapters").mkdir(parents=True)
    (site / "~orcast" / "adapters" / "old.py").touch()
    (site / "~orcast-1.0.0.dist-info").mkdir()
    (site / "torrcast").mkdir()
    (site / "torrcast" / "__init__.py").touch()

    done = subprocess.run(
        [
            "bash",
            "-c",
            f'{_funcs("drop_pip_leftovers")}\ndrop_pip_leftovers "$1"',
            "bash",
            str(site),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert sorted(item.name for item in site.iterdir()) == ["torrcast"], done.stdout


def _upgrading_predicate() -> str:
    """Однострочное определение ``upgrading()`` из install.sh, целиком и как есть."""
    found = [line for line in SCRIPT.splitlines() if line.startswith("upgrading() {")]
    assert len(found) == 1, "предиката upgrading() в install.sh нет или он не один"
    return found[0]


def _closing_line_block() -> str:
    """Настоящий блок закрывающей строки из install.sh, вырезанный по её тексту.

    Вырезается ФОРМОЙ, а не значением: пропадёт ветка обновления или переедет строка -
    вырезка не сойдётся и проба упадёт, а не тихо проверит копию прошлой правки.
    """
    head = SCRIPT.split("    if upgrading; then\n", 1)
    assert len(head) == 2, "в install.sh нет ветки закрывающей строки по upgrading"
    block, rest = head[1].split("\n    fi\n", 1)
    assert "done - try: cast <title>" in block, "вырезан не тот блок"
    assert "done - try: cast <title>" not in rest, "закрывающая строка есть и вне ветки"
    return "    if upgrading; then\n" + block + "\n    fi\n"


@pytest.mark.machine
@pytest.mark.parametrize(
    ("upgrade_from", "expected"),
    [("", "готово - смотри: cast <название>"), ("1.0.1", "torrcast 1.0.1 → 9.9.9 обновлено")],
)
def test_the_closing_line_says_updated_even_without_a_terminal(
    upgrade_from: str, expected: str
) -> None:
    """🔴 TC-887. Без терминала заставки нет, и закрывающее слово печатает эта строка.

    Поймано стендом: обновление по ssh заканчивалось словами «готово - смотри: cast»,
    и из вывода нельзя было узнать, состоялся переход или продукт поставили заново.
    """
    script = "\n".join(
        [
            "VERSION=9.9.9",
            f"UPGRADE_FROM={shlex.quote(upgrade_from)}",
            "LANGUAGE=ru",
            'log() { if [ "$LANGUAGE" = ru ]',
            '      then printf "%s\\n" "$2"; else printf "%s\\n" "$1"; fi; }',
            _upgrading_predicate(),
            _closing_line_block(),
        ]
    )
    done = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.strip() == expected, done.stdout + done.stderr


def fake_venv(box: Path) -> None:
    """Venv-заглушка в ``$PREFIX``: без неё настоящую фазу ``torrcast`` не прогнать.

    Настоящий venv тут не построить (``python3 -m venv`` на машине набора упирается в
    отсутствующий ensurepip), а pip тащил бы колесо из сети. Подделываются РОВНО две
    внешние вещи - pip и python самого venv'а; всё остальное в фазе настоящее: и порядок
    вызовов, и ``install -m 0755``, и сверка :func:`verify_torrcast`. Пакет в
    site-packages - копия дерева репы, поэтому сверка обязана сойтись, а ``prune_torrcast``
    работает по копии и до репы не дотягивается.
    """
    site = box / "site"
    shutil.copytree(
        REPO / "torrcast", site / "torrcast", ignore=shutil.ignore_patterns("__pycache__")
    )
    binder = box / "venv" / "bin"
    binder.mkdir(parents=True)
    (binder / "python").write_text(
        '#!/bin/sh\ncase "$*" in\n'
        f"  *sysconfig*) printf '%s\\n' {shlex.quote(str(site))} ;;\n"
        f"  *torrcast*) printf '%s\\n' {shlex.quote(str(site / 'torrcast'))} ;;\n"
        "  *) exit 1 ;;\nesac\n",
        encoding="utf-8",
    )
    for name in ("pip", "cast"):
        (binder / name).write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    for name in ("python", "pip", "cast"):
        (binder / name).chmod(0o755)


@pytest.mark.machine
def test_the_loader_lands_next_to_the_venv_for_upgrade_to_have_something_to_call(
    tmp_path: Path,
) -> None:
    """🔴 TC-887. Ровно этой строкой установки и жив ``cast --upgrade``.

    Обновление зовёт не второй загрузчик на питоне, а тот самый sh-файл из корня репы, и
    берёт его из ``$PREFIX``. В колесо он не попадает - pip ставит пакеты, - значит
    положить его туда обязана фаза установки. Перестанет класть - свежепоставленная копия
    ответит «нечем обновляться», продукт карточки умрёт, и ни один текстовый сторож этого
    не заметит: снятая строка не меняет ни слова в остальном скрипте. Поэтому мера гоняет
    НАСТОЯЩУЮ фазу до конца и смотрит, что после неё лежит в ``$PREFIX``.
    """
    box = tmp_path / "box"
    box.mkdir()
    fake_venv(box)
    done = subprocess.run(
        [str(REPO / "install.sh")],
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "TORRCAST_PHASES": "torrcast",
            "TORRCAST_NO_ROOT": "1",
            "TORRCAST_NO_SYSTEMD": "1",
            "TORRCAST_PREFIX": str(box),
            "TORRCAST_BIN_DIR": str(tmp_path / "bin"),
            "TORRCAST_CONFIG_DIR": str(tmp_path / "etc"),
            "TORRCAST_STATE_DIR": str(tmp_path / "var"),
            "TORRCAST_MOTD": str(tmp_path / "motd"),
            "TORRCAST_MOTD_D": str(tmp_path / "motd.d"),
            # Выбор индекса уже сделан: pick_pip_index не пойдёт спрашивать сеть.
            "PIP_INDEX_URL": "http://127.0.0.1:9/simple",
        },
    )

    printed = done.stdout + done.stderr
    assert done.returncode == 0, printed
    landed = box / "install"
    lying = sorted(item.name for item in box.iterdir())
    assert landed.is_file(), f"загрузчика в $PREFIX нет, лежит: {lying}"
    assert landed.stat().st_mode & 0o111, f"загрузчик не исполняем: {landed.stat().st_mode:o}"
    assert landed.read_bytes() == (REPO / "install").read_bytes(), "в $PREFIX лёг не тот файл"


def _rights_stand(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """Стенд поднятия прав: `id`, всегда говорящий «не root», и подставной sudo.

    🔴 Настоящий sudo в этой проверке участвовать не может НИ НА КАКОМ шаге: найдя его,
    установщик поднимется по-настоящему и пойдёт ставить продукт на машину, которая об
    этом не просила. Ровно так и вышло при первом замере вживую - поддельный `id`
    первым в PATH, настоящий sudo в хвосте того же PATH, полная установка от root.
    Поэтому чем поднимать права, установщику называют явно (`TORRCAST_SUDO`), а
    подставка только записывает, как её позвали, и ничего не запускает.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "id").write_text("#!/bin/sh\nprintf '1000\\n'\n", encoding="utf-8")
    (bindir / "id").chmod(0o755)
    calls = tmp_path / "sudo_calls.txt"
    sudo = tmp_path / "sudo"
    sudo.write_text(f'#!/bin/sh\nprintf "%s\\n" "$*" >> "{calls}"\n', encoding="utf-8")
    sudo.chmod(0o755)
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TORRCAST_SUDO": str(sudo),
    }
    env.pop("TORRCAST_NO_ROOT", None)
    env.pop("TORRCAST_LANGUAGE", None)
    return env, calls


@pytest.mark.machine
@pytest.mark.parametrize("language", ["ru", "en"])
def test_a_plain_user_is_restarted_through_sudo_with_the_named_tongue(
    tmp_path: Path, language: str
) -> None:
    """Не root - установщик не просит повторить себя руками, а перезапускает себя сам.

    Замер поведением: смотрим не текст install.sh, а то, чем на самом деле позвали
    sudo. Язык обязан ехать за sudo аргументом `env`, а не переменной окружения:
    настоящий sudo окружение вытирает молча (та же грабля куплена бутстрапом).
    """
    env, calls = _rights_stand(tmp_path)

    done = subprocess.run(
        [str(REPO / "install.sh"), f"-{language}"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )

    assert calls.exists(), f"sudo ни разу не был позван (stderr: {done.stderr!r})"
    asked = calls.read_text(encoding="utf-8").strip()
    assert f"TORRCAST_LANGUAGE={language}" in asked, (
        f"названный язык не пережил перезапуск через sudo: {asked!r}"
    )
    assert asked.endswith(str(REPO / "install.sh")), (
        f"sudo позвали не установщиком, а чем-то ещё: {asked!r}"
    )
    assert "restarting through sudo" in done.stderr or "перезапуск через sudo" in done.stderr


@pytest.mark.machine
def test_silence_about_the_tongue_stays_silence_across_sudo(tmp_path: Path) -> None:
    """🔴 TC-955. Не названный в этот заход язык за sudo не подставляется умолчанием:
    иначе повторная установка не-root'ом перебивала бы язык живого конфига."""
    env, calls = _rights_stand(tmp_path)

    subprocess.run([str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False)

    asked = calls.read_text(encoding="utf-8").strip()
    assert "TORRCAST_LANGUAGE" not in asked, f"молчание доехало словом: {asked!r}"


@pytest.mark.machine
def test_without_sudo_the_way_out_is_named_without_naming_sudo(tmp_path: Path) -> None:
    """Машина, где человек уже root, а sudo не поставлен вовсе (обычное дело в LXC),
    получала от нас команду, которой у неё нет. Отказ обязан звать к root, а не к sudo.
    """
    env, _ = _rights_stand(tmp_path)
    env["TORRCAST_SUDO"] = str(tmp_path / "no-such-sudo")

    done = subprocess.run(
        [str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False
    )

    assert done.returncode == 1
    assert "run as root" in done.stderr
    assert "sudo" not in done.stderr, f"sudo нет, а совет про sudo есть: {done.stderr!r}"


def test_the_rights_are_asked_about_before_anything_is_done() -> None:
    """Поднятие стоит раньше и заставки, и первой правки на диске: спросить пароль
    посреди установки значило бы бросить машину на полпути, а спросить его ВНУТРИ
    заставки - уронить её (TC-988, поднятие кончается `exec`)."""
    body = _body("become_root")
    entry = SCRIPT.split("# --- Точка входа ---", 1)[1]

    assert body.index('[ "$(id -u)" -eq 0 ]') < body.index('command -v "$SUDO"')
    assert "become_root" not in SCRIPT.split("main() {", 1)[1].split("\n}\n", 1)[0], (
        "поднятие снова внутри main, то есть внутри форкнутого работника заставки"
    )
    assert entry.index("become_root") < entry.index("ui_run real")
    assert entry.index("become_root") < entry.index('main "$@"')


@pytest.mark.machine
def test_the_restart_hands_root_its_own_home(tmp_path: Path) -> None:
    """🔴 TC-990. Поднятие идёт с `-H`, иначе у root остаётся HOME позвавшего.

    Тогда pip дважды за установку отказывается от кэша вслух («The cache has been
    disabled ... you should use sudo's -H flag») - и сам же называет этот ключ.
    Debian сбрасывает HOME и без ключа, macOS его хранит (`env_keep += "HOME MAIL"`),
    поэтому мерка тут - как позвали sudo, а не что вышло на этой машине.
    """
    env, calls = _rights_stand(tmp_path)

    subprocess.run([str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False)

    asked = calls.read_text(encoding="utf-8").strip()
    assert asked.split()[0] == "-H", f"поднятие идёт без -H: {asked!r}"


@pytest.mark.machine
def test_every_override_survives_the_restart_through_sudo(tmp_path: Path) -> None:
    """🔴 Куплено живым прогоном: `TORRCAST_PHASES="torrcast" ./install.sh` не-root'ом
    перезапустился под sudo БЕЗ этой переменной и вместо одной названной фазы прошёл
    установку целиком. Молчаливая потеря переопределения хуже отказа - человек просил
    одно, а машине сделали другое. Поэтому за sudo едут все TORRCAST_*, а не те, о
    которых вспомнил автор поднятия: мерка тут - переменная, которую поднятие не
    называет по имени нигде."""
    env, calls = _rights_stand(tmp_path)
    env["TORRCAST_PHASES"] = "torrcast"
    env["TORRCAST_PREFIX"] = str(tmp_path / "prefix")

    subprocess.run([str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False)

    asked = calls.read_text(encoding="utf-8").strip()
    assert "TORRCAST_PHASES=torrcast" in asked, f"названные фазы потерялись за sudo: {asked!r}"
    assert f"TORRCAST_PREFIX={tmp_path / 'prefix'}" in asked, (
        f"названный корень установки потерялся за sudo: {asked!r}"
    )


@pytest.mark.machine
@pytest.mark.skipif(os.geteuid() == 0, reason="root читает и нечитаемое - мерить нечем")
def test_a_config_the_user_cannot_read_does_not_replace_the_restart_with_a_refusal(
    tmp_path: Path,
) -> None:
    """🔴 Куплено живым прогоном на машине с уже поставленным продуктом. Конфиг лежит
    под root'ом, а язык из него установщик читает ДО поднятия прав: `[ -f ]` отвечал
    «да», sed падал «Permission denied», и `set -e` ронял установку ещё до первого её
    слова. Обычный пользователь получал отказ прав вместо перезапуска под sudo - то
    есть ровно на той машине, ради которой поднятие и заводилось."""
    env, calls = _rights_stand(tmp_path)
    etc = tmp_path / "etc"
    etc.mkdir()
    (etc / "config.json").write_text('{"language": "ru"}\n', encoding="utf-8")
    (etc / "config.json").chmod(0)
    env["TORRCAST_CONFIG_DIR"] = str(etc)

    done = subprocess.run(
        [str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False
    )

    assert calls.exists(), (
        f"перезапуска не было, установка легла раньше него (stderr: {done.stderr!r})"
    )
    assert "Permission denied" not in done.stderr


def _borrowed_home_stand(tmp_path: Path) -> tuple[dict[str, str], Path, Path]:
    """Стенд «мы уже root, а HOME чужой» - то самое, что даёт `sudo ./install.sh`.

    🔴 Настоящего root тут нет и не будет: `id` подставной, а `sudo` в этой ветке
    установщик не зовёт вовсе (:func:`become_root` уходит по первой же проверке).
    Прибор - подставной `rm`: он записывает HOME в момент ПЕРВОГО действия установки
    на диске (`cleanup_login_notice`) и передаёт вызов настоящему `rm`. Меряется
    поведение, а не текст: важно, чем HOME СТАЛ, а не какой ключ где написан.
    """
    bindir = tmp_path / "shim"
    bindir.mkdir()
    seen = tmp_path / "home_seen.txt"
    (bindir / "id").write_text(
        '#!/bin/sh\n[ "$1" = -u ] || exec /usr/bin/id "$@"\nprintf "0\\n"\n', encoding="utf-8"
    )
    (bindir / "id").chmod(0o755)
    (bindir / "rm").write_text(
        f'#!/bin/sh\nprintf "%s\\n" "$HOME" >> "{seen}"\nexec /bin/rm "$@"\n', encoding="utf-8"
    )
    (bindir / "rm").chmod(0o755)
    borrowed = tmp_path / "borrowed"
    borrowed.mkdir()
    for name in ("bin", "cfg", "state", "hls", "motd.d"):
        (tmp_path / name).mkdir()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "HOME": str(borrowed),
        "SUDO_USER": os.environ.get("USER", "tester"),
        "TORRCAST_PLAIN": "1",
        "TORRCAST_NO_SYSTEMD": "1",
        "TORRCAST_PHASES": "none",
        "TORRCAST_PREFIX": str(tmp_path / "prefix"),
        "TORRCAST_BIN_DIR": str(tmp_path / "bin"),
        "TORRCAST_CONFIG_DIR": str(tmp_path / "cfg"),
        "TORRCAST_STATE_DIR": str(tmp_path / "state"),
        "TORRCAST_HLS_DIR": str(tmp_path / "hls"),
        "TORRCAST_MOTD": str(tmp_path / "motd"),
        "TORRCAST_MOTD_D": str(tmp_path / "motd.d"),
    }
    env.pop("TORRCAST_NO_ROOT", None)
    env.pop("TORRCAST_LANGUAGE", None)
    return env, seen, borrowed


@pytest.mark.machine
def test_root_with_a_borrowed_home_takes_its_own_back(tmp_path: Path) -> None:
    """🔴 TC-990. `sudo ./install.sh` человек набирает сам, и за нашим `-H` там уже
    никого нет: HOME остаётся его, pip от root отказывается от кэша и говорит об
    этом дважды за установку. Замер на стенде с макоподобным sudoers показал ровно
    это: `./install.sh` обычным пользователем - ноль предупреждений, `sudo
    ./install.sh` там же - два. Поэтому дом чинится по факту, а не по тому, кто нас
    поднял."""
    env, seen, borrowed = _borrowed_home_stand(tmp_path)

    done = subprocess.run(
        [str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False
    )

    assert seen.exists(), f"установка не дошла до первого действия: {done.stderr[-800:]!r}"
    took = seen.read_text(encoding="utf-8").splitlines()[0]
    assert took != str(borrowed), "root пошёл ставить с домом позвавшего человека"
    assert took == os.path.expanduser("~root"), f"дом взят не root'ов: {took!r}"


def _defs_stand(tmp_path: Path, payload: bytes) -> tuple[list[str], dict[str, str], Path]:
    """Стенд определений индексеров: tar как на маке и архив с диска.

    Подделан ровно tar, и подделан ОДНОЙ чертой bsdtar - тем, что чужого ключа GNU
    он не знает и падает целиком, а не молча. Всё остальное уходит настоящему tar,
    поэтому распаковка меряется настоящая.
    """
    bindir = tmp_path / "bin"
    bindir.mkdir()
    real_tar = shutil.which("tar")
    assert real_tar, "в системе нет tar: мерить распаковку нечем"
    (bindir / "tar").write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do [ "$a" = --wildcards ] && { '
        'echo "bsdtar: Option --wildcards is not supported" >&2; exit 1; }; done\n'
        f'exec {real_tar} "$@"\n',
        encoding="utf-8",
    )
    (bindir / "tar").chmod(0o755)
    archive = tmp_path / "defs.tar.gz"
    archive.write_bytes(payload)
    for name in ("cfg", "state"):
        (tmp_path / name).mkdir()
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "TORRCAST_NO_ROOT": "1",
        "TORRCAST_NO_SYSTEMD": "1",
        "TORRCAST_PLAIN": "1",
        "TORRCAST_PHASES": "none",
        "TORRCAST_PREFIX": str(tmp_path / "prefix"),
        "TORRCAST_CONFIG_DIR": str(tmp_path / "cfg"),
        "TORRCAST_STATE_DIR": str(tmp_path / "state"),
        "TORRCAST_DEFS_TARBALL": archive.as_uri(),
    }
    env.pop("TORRCAST_LANGUAGE", None)
    # Позиционные доводы сбрасываются: сорсинг отдал бы путь установщику как ключ.
    call = ["bash", "-c", 'p="$1"; set --; . "$p"; seed_definitions', "_", str(REPO / "install.sh")]
    return call, env, tmp_path / "prefix" / "prowlarr-data" / "Definitions"


def _defs_archive(tmp_path: Path, count: int = 4) -> bytes:
    """Архив по образу Prowlarr/Indexers: определения v11 и мусор рядом с ними."""
    box = tmp_path / "src" / "Indexers-master"
    (box / "definitions" / "v11").mkdir(parents=True)
    (box / "definitions" / "v9").mkdir(parents=True)
    for i in range(count):
        (box / "definitions" / "v11" / f"probe{i}.yml").write_text(
            f"id: probe{i}\n", encoding="utf-8"
        )
    (box / "definitions" / "v9" / "old.yml").write_text("id: old\n", encoding="utf-8")
    (box / "README.md").write_text("# indexers\n", encoding="utf-8")
    tarball = tmp_path / "src" / "made.tar.gz"
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(box, arcname="Indexers-master")
    return tarball.read_bytes()


@pytest.mark.machine
def test_the_definitions_unpack_where_tar_is_bsdtar(tmp_path: Path) -> None:
    """🔴 TC-989. `--wildcards` - ключ GNU. На маке tar это bsdtar, и он падает
    целиком, а установка списывала это на «определения не скачались», хотя
    скачалось всё. Человек получал 3 индексера вместо 7 и совет искать сеть."""
    call, env, landed = _defs_stand(tmp_path, _defs_archive(tmp_path))

    done = subprocess.run(call, capture_output=True, text=True, env=env, check=False)

    printed = done.stdout + done.stderr
    assert done.returncode == 0, printed
    laid = sorted(item.name for item in landed.glob("*.yml"))
    assert [name for name in laid if name.startswith("probe")] == [
        f"probe{i}.yml" for i in range(4)
    ], f"определения не разложены, на диске: {laid}"
    assert "installed 6 definitions" in printed, printed
    assert "could not be downloaded" not in printed, printed


@pytest.mark.machine
def test_a_broken_archive_is_not_called_a_failed_download(tmp_path: Path) -> None:
    """Одна ветка на скачивание и распаковку врала о причине и уводила искать сеть.
    Скачалось - значит скачалось, и сказано об этом должно быть про распаковку."""
    call, env, _ = _defs_stand(tmp_path, b"\x1f\x8b\x08\x00not a tarball at all")

    done = subprocess.run(call, capture_output=True, text=True, env=env, check=False)

    printed = done.stdout + done.stderr
    assert "did not unpack" in printed, printed
    assert "could not be downloaded" not in printed, printed
