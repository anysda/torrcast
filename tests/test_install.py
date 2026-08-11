"""Ограждения критического пути установки.

Сам install.sh меняет систему, поэтому тест проверяет его контракт как текст:
добавление индексеров не уходит в фон, а отказ Prowlarr остаётся виден.
"""

from pathlib import Path

SCRIPT = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")


def _install_indexers() -> str:
    return SCRIPT.split("install_indexers() {", 1)[1].split("# --- 6.", 1)[0]


def test_indexers_are_added_one_at_a_time() -> None:
    body = _install_indexers()
    assert "INDEXER_ADD_GAP" in body
    assert 'sleep "$INDEXER_ADD_GAP"' in body
    assert "pids+=(" not in body


def test_an_add_failure_names_the_prowlarr_response_and_continues() -> None:
    body = _install_indexers()
    assert "Prowlarr ответил HTTP $status" in body
    assert " - не блокер" in body


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
