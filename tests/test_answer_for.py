"""Единственный вход сервера в маршруты страницы."""

from __future__ import annotations

import json

from web.answer_for import answer_for


def test_a_path_the_page_does_not_know_is_not_hers() -> None:
    """``None`` - это слово «не моё»: чужой путь остаётся прежним 404 у моста."""
    assert answer_for("GET", "/api/state", {}) is None
    assert answer_for("GET", "/api/whatever", {}) is None


def test_a_route_of_the_bridge_is_never_taken_by_the_page() -> None:
    for path in ("/api/state", "/api/play", "/api/control", "/api/next", "/api/resume"):
        assert answer_for("POST", path, {}) is None


def test_the_page_answers_her_own_path() -> None:
    found = answer_for("GET", "/api/phrases", {})

    assert found is not None
    assert found.code == 200
    assert "web.search.placeholder" in json.loads(found.body)


def test_the_query_string_is_cut_off_the_path_and_read() -> None:
    found = answer_for("GET", "/api/phrases?lang=ru", {})

    assert found is not None
    assert json.loads(found.body)["web.shelf.new"] == "Новинки"


def test_one_name_asked_twice_is_one_value() -> None:
    found = answer_for("GET", "/api/phrases?lang=ru&lang=en", {})

    assert found is not None
    assert json.loads(found.body)["web.shelf.new"] == "Новинки"


def test_a_percent_encoded_walk_up_does_not_reach_out_of_the_page() -> None:
    """Разкодировать путь обязан именно этот вход: иначе ``%2e%2e`` доедет до диска."""
    found = answer_for("GET", "/static/%2e%2e/%2e%2e/pyproject.toml", {})

    assert found is not None
    assert found.code == 404


def test_the_method_is_part_of_the_question() -> None:
    assert answer_for("POST", "/api/phrases", {}) is None
