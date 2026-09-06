"""Отказ страницы: тело у него такое же, как у моста."""

from __future__ import annotations

import json

from web.answer import JSON
from web.refusal import refusal


def test_a_refusal_speaks_one_word_in_json() -> None:
    answer = refusal(404, "not_found")

    assert answer.code == 404
    assert json.loads(answer.body) == {"error": "not_found"}


def test_a_refusal_is_signed_as_json() -> None:
    assert refusal(409, "already_playing").kind == JSON


def test_the_code_is_the_callers_and_not_a_constant() -> None:
    assert [refusal(code, "no").code for code in (400, 404, 409)] == [400, 404, 409]
