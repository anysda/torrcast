"""Раздача самой страницы и её файлов."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from web.request import Request
from web.serve_static import STATIC, serve_static


def _ask(path: str) -> tuple[int, bytes, str]:
    answer = serve_static(Request("GET", path, {}, {}))
    return answer.code, answer.body, answer.kind


def test_the_root_path_gives_the_page_itself() -> None:
    code, body, kind = _ask("/")

    assert code == 200
    assert kind == "text/html; charset=utf-8"
    assert b"tc-root" in body


def test_every_kind_the_page_needs_is_signed_by_its_own_type() -> None:
    signed = {
        "/static/style.css": "text/css; charset=utf-8",
        "/static/app.js": "text/javascript; charset=utf-8",
        "/static/hls-1.5.17.min.js": "text/javascript; charset=utf-8",
        "/static/fonts/archivo-latin.woff2": "font/woff2",
    }

    assert {path: _ask(path)[2] for path in signed} == signed


def test_the_vendored_player_arrives_whole() -> None:
    code, body, _kind = _ask("/static/hls-1.5.17.min.js")

    assert code == 200
    assert len(body) == (STATIC / "hls-1.5.17.min.js").stat().st_size


def test_a_walk_up_does_not_escape_the_page() -> None:
    """Выход наружу отвечает 404 и НЕ отдаёт байтов: проверяется и то, и другое."""
    for path in (
        "/static/../pyproject.toml",
        "/static/../../etc/passwd",
        "/static/fonts/../../pyproject.toml",
        "/static//etc/passwd",
    ):
        code, body, _kind = _ask(path)
        assert code == 404, path
        assert json.loads(body) == {"error": "not_found"}, path


def test_a_link_pointing_out_of_the_page_is_the_same_walk_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    outside = tmp_path / "secret.css"
    outside.write_text("body{}", encoding="utf-8")
    home = tmp_path / "static"
    home.mkdir()
    (home / "link.css").symlink_to(outside)
    monkeypatch.setattr("web.serve_static.STATIC", home)

    assert _ask("/static/link.css")[0] == 404


def test_a_file_edited_between_two_calls_arrives_new(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Кэша у страницы нет: правка обязана доехать следующим же запросом."""
    home = tmp_path / "static"
    home.mkdir()
    (home / "style.css").write_text("body{color:red}", encoding="utf-8")
    monkeypatch.setattr("web.serve_static.STATIC", home)
    before = _ask("/static/style.css")

    (home / "style.css").write_text("body{color:lime}", encoding="utf-8")
    after = _ask("/static/style.css")

    assert before[1] == b"body{color:red}"
    assert after[1] == b"body{color:lime}"


def test_the_page_is_never_kept_in_a_cache() -> None:
    answer = serve_static(Request("GET", "/static/style.css", {}, {}))

    assert dict(answer.headers())["Cache-Control"] == "no-store"


def test_a_name_that_is_not_a_file_is_a_stranger() -> None:
    assert _ask("/static/")[0] == 404
    assert _ask("/static/fonts")[0] == 404
    assert _ask("/static/nothing-like-this.css")[0] == 404
