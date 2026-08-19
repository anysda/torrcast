"""Ограждения критического пути установки.

Сам install.sh меняет систему, поэтому тест проверяет его контракт как текст:
добавление индексеров не уходит в фон, а отказ Prowlarr остаётся виден.
"""

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

REPO = Path(__file__).parents[1]
SCRIPT = (REPO / "install.sh").read_text(encoding="utf-8")


def _body(name: str) -> str:
    return SCRIPT.split(f"{name}() {{", 1)[1].split("\n}", 1)[0]


def _install_indexers() -> str:
    return SCRIPT.split("install_indexers() {", 1)[1].split("# --- 6.", 1)[0]


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
    assert '"anilibria|http://127.0.0.1:9697/"' in SCRIPT
    assert "'anilibria.top|/api/v1/app/search/releases?query=Kaiba||" in SCRIPT
    assert '"$REPO_DIR/definitions/anilibria.yml"' in SCRIPT


def test_jacred_is_a_regular_indexer_with_a_shim_route() -> None:
    assert '"jacred|http://127.0.0.1:9698/"' in SCRIPT
    assert "'api.jacred.su|/api/search?query=matrix&sort=sid&limit=100||" in SCRIPT
    assert '"$REPO_DIR/definitions/jacred.yml"' in SCRIPT


def test_install_removes_its_login_notice_without_a_motd_phase() -> None:
    phases = SCRIPT.split('PHASES="', 1)[1].split('"', 1)[0]
    assert "cleanup_login_notice() {" in SCRIPT
    cleanup = SCRIPT.split("cleanup_login_notice() {", 1)[1].split("\n}", 1)[0]

    assert "motd" not in phases
    assert 'rm -f "$motd_d/00-torrcast"' in cleanup
    assert "cast status | stop | doctor" in cleanup
    assert "cleanup_login_notice" in SCRIPT.split("main() {", 1)[1]


def test_imdb_files_follow_the_state_directory() -> None:
    assert 'IMDB_RATINGS_PATH="${TORRCAST_IMDB_RATINGS_PATH:-$STATE_DIR/imdb-ratings.tsv}"' in SCRIPT
    assert 'IMDB_NAMES_PATH="${TORRCAST_IMDB_NAMES_PATH:-$STATE_DIR/imdb-ru-names.tsv}"' in SCRIPT


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
    assert 'reserve="$(warm_budget)" || return 1' in _body("ts_cache_disk")
    assert 'disk="$(ts_cache_disk)" || return 1' in _body("ts_cache_place")
    assert 'place="$(ts_cache_place)" || die' in _body("install_torrserver")


def test_core_sources_are_the_two_the_catalog_stands_on() -> None:
    """🔴 TC-692. Опорные - те, без которых пул пуст: метапоиск и русский трекер."""
    assert 'CORE_INDEXERS=("$KEY_INDEXER" "rutor")' in SCRIPT
    assert "core_indexer" in _body("late_indexer")


def test_the_catalog_gate_asks_the_search_not_the_list() -> None:
    """🔴 TC-692. «Числится» и «отвечает» - разные утверждения: rutor стоял в списке
    включённым и не отдавал ничего, а установка объявляла успех. Гейт спрашивает поиск."""
    gate = _body("catalog_gate")
    assert "/api/v1/search" in gate
    assert "не завёлся" in gate and "не отдал ничего" in gate
    assert 'CATALOG_CUT="$cut"' in gate
    # Опорные щупаются на глазах, поэтому в догрев (`check_indexers`) они не уезжают.
    assert 'core_indexer "$def" || rest+=(' in _install_indexers()


def test_a_cut_catalog_is_not_a_successful_install() -> None:
    """🔴 TC-692. Пустой каталог под видом успеха - неправда и для человека, и для
    автоматики: последнее слово установки называет урез и возвращает ненулевой код."""
    main = _body("main")
    assert 'if [ -n "$CATALOG_CUT" ]; then' in main
    assert 'exit "$EXIT_CATALOG_CUT"' in main
    assert "EXIT_CATALOG_CUT=2" in SCRIPT


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


def _stub_prowlarr(fail: frozenset[str], silent: frozenset[str]) -> tuple[ThreadingHTTPServer, int]:
    """Заглушка Prowlarr: отвечает как живой, но кого щупать успешно - решаем мы.

    Живой Prowlarr на молчащий трекер отвечает 400 с телом про 502, а забаненный
    индексер у него числится включённым и отдаёт пустой поиск - обе беды здесь и
    инсценируются, потому что от канала их не дождёшься по заказу.
    """
    added: list[dict[str, object]] = []

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
            if body.get("name") in fail:
                return self._send(400, [{"errorMessage": "Unable to connect to indexer"}])
            body["id"] = len(added) + 1
            added.append(body)
            return self._send(201, body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, server.server_port


def _run_indexers(
    box: Path, fail: frozenset[str] = frozenset(), silent: frozenset[str] = frozenset()
) -> subprocess.CompletedProcess[str]:
    """Прогнать фазу индексеров установки против заглушки Prowlarr."""
    server, port = _stub_prowlarr(fail, silent)
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
        "TORRCAST_INDEXER_RETRY_TIMES": "1",
        "TORRCAST_INDEXER_RETRY_EVERY": "1",
    }
    try:
        return subprocess.run(
            [str(REPO / "install.sh")], capture_output=True, text=True, env=env, check=False
        )
    finally:
        server.shutdown()


@pytest.mark.machine
def test_a_cut_catalog_comes_out_of_the_installer_as_a_failure(tmp_path: Path) -> None:
    """🔴 TC-692. Мера меряет ЦЕЛЬ: гоняем саму фазу и смотрим её КОД ВОЗВРАТА.

    Симптом карточки: на чистой установке оба опорных источника получали от Prowlarr
    400, установка печатала «не блокер» и объявляла успех - каталог при этом был пуст.
    Проба инсценирует ровно это, и красным обязан быть код возврата, а не только слова.
    """
    done = _run_indexers(tmp_path / "оба-отказали", fail=frozenset({"Knaben", "RuTor"}))
    assert done.returncode == 2, done.stdout + done.stderr
    printed = done.stdout + done.stderr
    assert "каталог урезан: Knaben (не завёлся), RuTor (не завёлся)" in printed
    assert "не блокер" not in printed


@pytest.mark.machine
def test_a_listed_but_silent_core_source_is_a_cut_catalog_too(tmp_path: Path) -> None:
    """🔴 TC-692. Заведён - не значит отвечает: живьём rutor стоял в списке включённым и
    молчал, а прежняя проверка «добавился ли» такую установку объявляла успешной."""
    done = _run_indexers(tmp_path / "молчит", silent=frozenset({"RuTor"}))
    assert done.returncode == 2, done.stdout + done.stderr
    assert "RuTor (заведён, но не отдал ничего)" in done.stdout + done.stderr


@pytest.mark.machine
def test_the_installer_still_succeeds_when_the_core_sources_answer(tmp_path: Path) -> None:
    """🔴 TC-692. Отрицательная проба к гейту: он обязан УМЕТЬ пропускать. Иначе красный
    код возврата ничего не говорит - его отдавала бы любая установка."""
    done = _run_indexers(tmp_path / "все-ответили")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "каталог урезан" not in done.stdout + done.stderr
    assert "Knaben отвечает: 3 раздач" in done.stdout
