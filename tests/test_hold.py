"""``POST /api/hold``: страница называет записи, чьи раздачи держатся подключёнными."""

from __future__ import annotations

import pytest

import web.hold
from torrcast.domain.json_value import JsonValue
from web.answer import Answer
from web.hold import hold
from web.request import Request


class _Holder:
    def __init__(self) -> None:
        self.touched: list[tuple[str, list[str]]] = []

    def touch(self, base_url: str, keys: list[str]) -> int:
        self.touched.append((base_url, keys))
        return len(keys)


class _Config:
    torrserver_url = "http://ts:8090"


def _post(body: dict[str, JsonValue], monkeypatch: pytest.MonkeyPatch) -> tuple[_Holder, Answer]:
    holder = _Holder()
    monkeypatch.setattr(web.hold, "RECORD_HOLD", holder)
    monkeypatch.setattr(web.hold, "load_config", _Config)
    return holder, hold(Request(method="POST", path="/api/hold", query={}, body=body))


def test_the_keys_the_page_names_are_handed_to_the_holder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    holder, answer = _post({"keys": ["movie:тачки:2006", "", 7, "x" * 301, "s"]}, monkeypatch)

    assert answer.code == 200
    assert holder.touched == [("http://ts:8090", ["movie:тачки:2006", "s"])]


@pytest.mark.parametrize("keys", [None, "movie:тачки:2006", {"a": 1}])
def test_a_body_without_a_key_list_is_refused(
    keys: JsonValue, monkeypatch: pytest.MonkeyPatch
) -> None:
    holder, answer = _post({"keys": keys}, monkeypatch)

    assert answer.code == 400
    assert holder.touched == []
