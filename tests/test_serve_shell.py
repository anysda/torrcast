"""Оболочка страницы под адресом карточки (``/card/*``)."""

from __future__ import annotations

from web.request import Request
from web.serve_shell import serve_shell


def _ask(path: str) -> tuple[int, bytes, str]:
    answer = serve_shell(Request("GET", path, {}, {}))
    return answer.code, answer.body, answer.kind


def test_any_card_address_gives_the_same_page_shell() -> None:
    for path in ("/card/tt0816692", "/card/some-key", "/card/"):
        code, body, kind = _ask(path)
        assert code == 200, path
        assert kind == "text/html; charset=utf-8", path
        assert b"tc-root" in body, path
