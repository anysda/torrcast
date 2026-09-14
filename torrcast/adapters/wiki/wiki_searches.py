"""Поиск статей после промаха прямых заголовков; зовёт добор справки."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Mapping
from typing import Any

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import WIKI_HOST, WIKI_PATH
from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.latin_title import latin_title
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.facts.search_params import search_params
from torrcast.domain.facts.settings import _EXLIMIT
from torrcast.domain.facts.titles_for import titles_for
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_ranked import wiki_ranked
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_map import json_map
from torrcast.domain.slugify import slugify
from torrcast.ports.json_client import JsonClient
from torrcast.ports.ru_names import RuNames


def wiki_searches(
    client: JsonClient,
    wanted: list[tuple[str, int | None]],
    timeout: float,
    kinds: Mapping[tuple[str, int | None], str] | None = None,
    foreground: bool = False,
    names: RuNames | None = None,
) -> tuple[dict[tuple[str, int | None], list[str]], list[Any], set[tuple[str, int | None]]]:
    """Search the names that direct extraction could not identify.

    A complete direct title wave proves only that our guessed headings did not work.
    Search is the product's other article route, so an empty fact is lawful only after
    it too replied.  ``read_origin`` keeps the same title, type and identity gates as
    passports; a search rank alone must never select a different work.

    Search ranks the neighbours of a Latin franchise name above the picture itself:
    ``Avatar фильм`` brings the sequels and a game, not «Аватар» of 2009.  The IMDb map
    knows the Russian release name, and its headings join the same wave.  A heading
    counts only when its article names the asked original, and the picture is answered
    only when both requests replied.
    """
    selected: dict[tuple[str, int | None], list[str]] = {}
    replies: list[Any] = []
    answered: set[tuple[str, int | None]] = set()
    renamed = (
        names.ru_names([(*key, (kinds or {}).get(key, "movie")) for key in wanted]) if names else {}
    )
    looked: dict[tuple[str, int | None], list[str]] = {}
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

    def look(key: tuple[str, int | None]) -> None:
        kind = (kinds or {}).get(key, "movie")
        titles = list(dict.fromkeys(t for n in renamed[key] for t in titles_for(n, key[1], kind)))
        titles = titles[:_EXLIMIT]
        with contextlib.suppress(Exception):
            payload = client.get(
                WIKI_HOST, WIKI_PATH, extract_params(titles), {}, timeout, foreground=foreground
            )
            if not isinstance(json_map(json_map(payload).get("query")).get("pages"), list):
                return
            hops, pages = wiki_pages(payload)
            origin = [
                title
                for title in titles
                if (page := _article(title, hops, pages)) is not None
                and _names_original(key[0], str(page.get("title") or ""), page.get("extract"))
            ]
            with lock:
                replies.append(payload)
                looked[key] = origin

    wave = [threading.Thread(target=ask, args=(key,), daemon=True) for key in wanted]
    wave += [threading.Thread(target=look, args=(key,), daemon=True) for key in renamed]
    for thread in wave:
        thread.start()
    # Five Wikipedia host lanes serve this wave.  The next card has foreground
    # priority there, while this caller still closes its own threads afterwards.
    rounds = (len(wave) + 4) // 5
    got, found, heard, chosen = closed_wave(
        wave,
        time.monotonic() + timeout * rounds,
        lambda: (list(replies), dict(looked), set(answered), dict(selected)),
    )
    for key, origin in found.items():
        if origin:
            chosen[key] = [*chosen.get(key, []), *origin]
    return chosen, got, {key for key in heard if key not in renamed or key in found}


def _names_original(title: str, heading: str, extract: object) -> bool:
    """Whether a Russian release heading is the asked Latin picture rather than a namesake.

    The article naming the asked original proves it.  A stub such as «Муза (фильм)»,
    «кинофильм 1999 года», names none; its film qualifier still separates it from the bare
    heading, which is the Muses of mythology or the Hindu avatar.  An article naming a
    different original is another picture.
    """
    latin = slugify(latin_title(str(extract or "")))
    return latin == slugify(title) or (not latin and " (" in heading)
