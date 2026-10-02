"""Раздача пишется в базу службы один раз: запись переписывает базу под общим замком."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.torrserver.add_once import add_once


def _service(data: str) -> tuple[list[object], Any]:
    saves: list[object] = []

    def post(path: str, body: dict[str, Any]) -> dict[str, str]:
        saves.append(body["save_to_db"])
        return {"hash": "abc", "data": data}

    return saves, post


def test_a_new_torrent_is_written_to_the_base() -> None:
    saves, post = _service(data="")

    assert add_once(post, "magnet:?xt=urn:btih:abc")["hash"] == "abc"

    assert saves == [False, True], "кэш раздачи переживает перезапуск службы (TC-734)"


def test_a_torrent_the_base_already_holds_is_added_without_a_write() -> None:
    saves, post = _service(data='{"TorrServer":{"Files":[]}}')

    add_once(post, "magnet:?xt=urn:btih:abc")

    assert saves == [False]
