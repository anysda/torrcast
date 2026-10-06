"""Идёт ли показ со стороны службы раздач: читатели у раздач, которые не только в базе."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.torrserver.reading import reading
from torrcast.domain.server_down_error import ServerDownError


def _service(listed: Any, readers: dict[str, list[object]]) -> tuple[Any, list[str]]:
    asked: list[str] = []

    def post(path: str, body: dict[str, Any]) -> Any:
        if path == "/torrents":
            return listed
        asked.append(body["hash"])
        return {"Readers": readers.get(body["hash"])}

    return post, asked


def test_a_torrent_with_readers_means_a_show_is_running() -> None:
    post, _ = _service([{"hash": "a", "stat": 3}, {"hash": "b", "stat": 3}], {"b": [{}, {}]})
    assert reading(post) is True


def test_torrents_nobody_reads_mean_no_show() -> None:
    post, asked = _service([{"hash": "a", "stat": 3}, {"hash": "db", "stat": 5}], {"a": []})
    assert reading(post) is False
    assert asked == ["a"], "раздачу только из базы никто не читает: о ней не спрашиваем"


def test_a_service_that_did_not_say_is_unknown() -> None:
    def post(_path: str, _body: dict[str, Any]) -> Any:
        raise ServerDownError("TorrServer does not answer")

    assert reading(post) is None
    assert reading(_service({"odd": 1}, {})[0]) is None
