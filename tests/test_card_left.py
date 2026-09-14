"""``POST /api/card-left``: уход с карточки снимает прогрев её раздачи."""

from __future__ import annotations

import pytest

import web.card_left
from torrcast.domain.json_value import JsonValue
from web.answer import Answer
from web.card_left import card_left
from web.request import Request


class _Warms:
    def __init__(self) -> None:
        self.left: list[str] = []

    def leave(self, key: str) -> None:
        self.left.append(key)


def _post(body: dict[str, JsonValue], monkeypatch: pytest.MonkeyPatch) -> tuple[_Warms, Answer]:
    warms = _Warms()
    monkeypatch.setattr(web.card_left, "CARD_WARM", warms)
    return warms, card_left(Request(method="POST", path="/api/card-left", query={}, body=body))


def test_the_card_the_page_left_is_named_to_the_warm(monkeypatch: pytest.MonkeyPatch) -> None:
    warms, answer = _post({"picture": "movie:тачки:2006"}, monkeypatch)

    assert answer.code == 204
    assert warms.left == ["movie:тачки:2006"]


@pytest.mark.parametrize("picture", [None, "", 7, "x" * 301])
def test_a_body_without_a_picture_key_is_refused(
    picture: JsonValue, monkeypatch: pytest.MonkeyPatch
) -> None:
    warms, answer = _post({"picture": picture}, monkeypatch)

    assert answer.code == 400
    assert warms.left == []
