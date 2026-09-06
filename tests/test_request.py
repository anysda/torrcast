"""Разобранный запрос к странице."""

from __future__ import annotations

import pytest

from web.request import Request


def test_a_request_keeps_what_it_was_asked() -> None:
    request = Request("GET", "/api/phrases", {"lang": "ru"}, {})

    assert request.method == "GET"
    assert request.path == "/api/phrases"
    assert request.query["lang"] == "ru"
    assert request.body == {}


def test_a_request_carries_the_body_of_a_post() -> None:
    request = Request("POST", "/api/web/position", {}, {"pos": 41.0, "key": "movie:x"})

    assert request.body["pos"] == 41.0
    assert request.body["key"] == "movie:x"


def test_a_request_cannot_be_edited_after_it_is_made() -> None:
    request = Request("GET", "/", {}, {})

    with pytest.raises(AttributeError):
        request.path = "/other"  # type: ignore[misc]
