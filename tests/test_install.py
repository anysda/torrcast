"""Ограждения критического пути установки.

Сам install.sh меняет систему, поэтому тест проверяет его контракт как текст:
добавление индексеров не уходит в фон, а отказ Prowlarr остаётся виден.
"""

import json
import os
import shlex
import subprocess
import sys
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
    assert 'late_run "индексер $names (добавляется до двух минут)" add_indexers' in body
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
            began = text.count(" | начал: ")
            ended = text.count(" | готово: ") + text.count(" | НЕ вышло ")
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
    done, _ = _run_indexers(tmp_path / "оба-отказали", fail=frozenset({"Knaben", "RuTor"}))
    assert done.returncode == 2, done.stdout + done.stderr
    printed = done.stdout + done.stderr
    assert "каталог урезан: Knaben (не завёлся), RuTor (не завёлся)" in printed
    assert "не блокер" not in printed


@pytest.mark.machine
def test_a_listed_but_silent_core_source_is_a_cut_catalog_too(tmp_path: Path) -> None:
    """🔴 TC-692. Заведён - не значит отвечает: живьём rutor стоял в списке включённым и
    молчал, а прежняя проверка «добавился ли» такую установку объявляла успешной."""
    box = tmp_path / "молчит"
    done, posts = _run_indexers(box, silent=frozenset({"RuTor"}))
    assert done.returncode == 2, done.stdout + done.stderr
    assert "RuTor (заведён, но не отдал ничего)" in done.stdout + done.stderr
    # 🔴 TC-697. Заведшийся индексер не переспрашивается: «завёлся и молчит» - не
    # повод для второго обращения, его судьбу решает гейт поиском, а не повторным POST.
    _late_settled(box)
    assert len(posts["RuTor"]) == 1 and len(posts["Knaben"]) == 1


@pytest.mark.machine
def test_the_installer_still_succeeds_when_the_core_sources_answer(tmp_path: Path) -> None:
    """🔴 TC-692. Отрицательная проба к гейту: он обязан УМЕТЬ пропускать. Иначе красный
    код возврата ничего не говорит - его отдавала бы любая установка."""
    box = tmp_path / "все-ответили"
    done, posts = _run_indexers(box)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "каталог урезан" not in done.stdout + done.stderr
    assert "Knaben отвечает: 3 раздач" in done.stdout
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
    assert "каталог этим не урезан" in done.stdout + done.stderr
    _late_settled(box)
    # Узкие приходят обеими дорогами - из фона (yts) и с глаз (Nyaa.si), и обе спрашивают
    # ровно раз; заведшийся узкий не переспрашивается тем более.
    for name in ("YTS", "Nyaa.si", "JacRed"):
        assert len(posts[name]) == 1, f"{name}: обращений {len(posts[name])} вместо одного"


def _shim_knobs() -> list[str]:
    """Ручки шима так, как их запишет установка: значения подставляет сам bash."""
    body = SCRIPT.split("local knobs; knobs=", 1)[1].split('Sockets=torrcast-shim.socket"', 1)[0]
    agent = SCRIPT.split('\nUA="', 1)[1].split('"\n', 1)[0]
    snippet = (
        f'UA="{agent}"\n'
        "HOSTS_FILE=/etc/hosts\nSHIM_PID=/etc/torrcast-shim/shim.pid\n"
        "SHIM_DIR=/etc/torrcast-shim\npins=api.knaben.org\nROUTE_EVERY=900\n"
        "PROBE_TIMEOUT=25\nPROBE_STALL=5\nPROBE_FLOOR=1024\n"
        f'knobs={body}Sockets=torrcast-shim.socket"\nprintf "%s\\n" "$knobs"\n'
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
