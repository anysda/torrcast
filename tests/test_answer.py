"""Ответ маршрута страницы: код, тело и подпись под ним."""

from __future__ import annotations

import pytest

from web.answer import JSON, NO_STORE, Answer


def test_headers_name_the_type_the_cache_and_the_length() -> None:
    answer = Answer(200, b"hello")

    assert answer.headers() == (
        ("Content-Type", JSON),
        ("Cache-Control", NO_STORE),
        ("Content-Length", "5"),
    )


def test_length_is_counted_in_bytes_not_in_letters() -> None:
    """Кириллическая надпись длиннее себя в байтах: длина по знакам обрывает тело."""
    answer = Answer(200, "привет".encode())

    assert dict(answer.headers())["Content-Length"] == "12"


def test_the_type_and_the_cache_are_the_answers_own() -> None:
    answer = Answer(200, b"body{}", kind="text/css; charset=utf-8", cache="max-age=60")

    assert dict(answer.headers())["Content-Type"] == "text/css; charset=utf-8"
    assert dict(answer.headers())["Cache-Control"] == "max-age=60"


def test_an_answer_cannot_be_edited_after_it_is_made() -> None:
    answer = Answer(404, b"{}")

    with pytest.raises(AttributeError):
        answer.code = 200  # type: ignore[misc]
