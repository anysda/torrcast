"""``POST /api/card-left``: уход с карточки снимает прогрев её раздачи."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import web.card_left
from torrcast.domain.json_value import JsonValue
from web.answer import Answer
from web.card_left import card_left
from web.request import Request


class _Warms:
    def __init__(self, released: bool = True) -> None:
        self.left: list[str] = []
        self.heads: list[str] = []
        self.released = released

    def leave(self, key: str) -> bool:
        self.left.append(key)
        return self.released


def _post(
    body: dict[str, JsonValue], monkeypatch: pytest.MonkeyPatch, released: bool = True
) -> tuple[_Warms, Answer]:
    warms = _Warms(released)
    monkeypatch.setattr(web.card_left, "CARD_WARM", warms)
    monkeypatch.setattr(web.card_left, "HEAD", SimpleNamespace(drop=warms.heads.append))
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


def test_the_head_of_the_card_goes_with_its_warm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Прогрев снят - снята и голова этой картины: играть её не будут."""
    warms, _answer = _post({"picture": "movie:тачки:2006"}, monkeypatch)

    assert warms.heads == ["movie:тачки:2006"]


def test_a_card_the_show_took_keeps_its_head(monkeypatch: pytest.MonkeyPatch) -> None:
    """Страница ушла с карточки на показ: стенд у показа, и голову ждёт его первый кадр."""
    warms, _answer = _post({"picture": "movie:тачки:2006"}, monkeypatch, released=False)

    assert warms.heads == []
