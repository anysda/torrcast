"""Поиск статей после промаха прямых заголовков; зовёт добор справки."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Mapping
from typing import Any

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import WIKI_HOST, WIKI_PATH
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.facts.search_params import search_params
from torrcast.domain.facts.wiki_ranked import wiki_ranked
from torrcast.domain.json_map import json_map
from torrcast.ports.json_client import JsonClient


def wiki_searches(
    client: JsonClient,
    wanted: list[tuple[str, int | None]],
    timeout: float,
    kinds: Mapping[tuple[str, int | None], str] | None = None,
    foreground: bool = False,
) -> tuple[dict[tuple[str, int | None], list[str]], list[Any], set[tuple[str, int | None]]]:
    """Search the names that direct extraction could not identify.

    A complete direct title wave proves only that our guessed headings did not work.
    Search is the product's other article route, so an empty fact is lawful only after
    it too replied.  ``read_origin`` keeps the same title, type and identity gates as
    passports; a search rank alone must never select a different work.
    """
    selected: dict[tuple[str, int | None], list[str]] = {}
    replies: list[Any] = []
    answered: set[tuple[str, int | None]] = set()
    lock = threading.Lock()

    def ask(key: tuple[str, int | None]) -> None:
        title, _year = key
        kind = (kinds or {}).get(key, "movie")
        query = f"{title} {'сериал' if kind == 'tv' else 'фильм'}"
        with contextlib.suppress(Exception):
            payload = client.get(
                WIKI_HOST, WIKI_PATH, search_params(query), {}, timeout, foreground=foreground
            )
            raw = json_map(payload)
            if "error" in raw or not ("query" in raw or "batchcomplete" in raw):
                return
            series = kind == "tv"
            page = next(
                (row for row in wiki_ranked(payload) if read_origin([row], title, series=series)),
                None,
            )
            with lock:
                replies.append(payload)
                answered.add(key)
                heading = page.get("title") if isinstance(page, dict) else None
                if isinstance(heading, str):
                    selected[key] = [heading]

    wave = [threading.Thread(target=ask, args=(key,), daemon=True) for key in wanted]
    for thread in wave:
        thread.start()
    # Five Wikipedia host lanes serve this wave.  The next card has foreground
    # priority there, while this caller still closes its own threads afterwards.
    rounds = (len(wave) + 4) // 5
    replies = closed_wave(wave, time.monotonic() + timeout * rounds, lambda: list(replies))
    return selected, replies, answered
