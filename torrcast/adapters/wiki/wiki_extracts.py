"""Пакетный запрос статей Википедии для справки меню."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Mapping
from typing import Any

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import WIKI_HOST, WIKI_PATH
from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.settings import _EXBATCHES, _EXLIMIT
from torrcast.domain.facts.titles_for import titles_for
from torrcast.domain.facts.wiki_reply import _merged
from torrcast.domain.json_map import json_map
from torrcast.ports.json_client import JsonClient

_LANES = 5


def wiki_extracts(
    client: JsonClient,
    wanted: list[tuple[str, int | None]],
    timeout: float,
    kinds: Mapping[tuple[str, int | None], str] | None = None,
    foreground: bool = False,
) -> tuple[
    dict[tuple[str, int | None], list[str]],
    dict[str, Any],
    set[tuple[str, int | None]],
    set[tuple[str, int | None]],
]:
    """Запросить кандидатов волной и назвать полностью отвеченные картины.

    Кандидатов на статью у картины около десятка (:func:`titles_for`), а в один запрос
    влезает :data:`_EXLIMIT`. Пока запрос был один, лишние кандидаты отбрасывались, и
    это стоило самой справки: замер на ста настоящих меню (503 картины) дал статью у
    49% картин по одной, но только у 14% при пакете из двадцати имён.

    Поэтому имена режутся на пакеты и уезжают РАЗОМ: запросы ждут сеть, а не друг друга.
    Замер на том же корпусе: один пакет 0.78 с, три очередью 2.14 с, три разом 0.83 с -
    втрое больше имён за семь сотых секунды.

    Тип картины правит ПОРЯДОК кандидатов (:func:`titles_for`), а не их набор: в волну
    влезает не всё, и уточнение чужого типа впереди своего стоит места настоящей статьи.

    Имена ВСЕХ спрошенных картин едут в перебор каждой: имя соседа по вопросу - не
    кандидат, а чужой адрес, и отрезанный подзаголовок не вправе его занимать
    (:func:`titles_for`).

    ``answered`` называет картины, чьи назначенные пакеты ответили все; промолчавший
    пакет не говорит про свои имена ничего, и это «не успели спросить», а не «статьи нет».
    """
    names_asked = [key[0] for key in wanted]
    candidates = {key: titles_for(*key, (kinds or {}).get(key, ""), names_asked) for key in wanted}
    names: list[str] = []
    scheduled: dict[tuple[str, int | None], list[str]] = {key: [] for key in wanted}
    room = _EXLIMIT * _EXBATCHES
    for depth in range(max((len(c) for c in candidates.values()), default=0)):
        for key in wanted:
            if depth < len(candidates[key]) and len(names) < room:
                names.append(candidates[key][depth])
                scheduled[key].append(candidates[key][depth])
    answers: list[tuple[list[str], Any]] = []
    lock = threading.Lock()

    def ask(part: list[str]) -> None:
        with contextlib.suppress(Exception):
            payload = client.get(
                WIKI_HOST, WIKI_PATH, extract_params(part), {}, timeout, foreground=foreground
            )
            # HTTP 200 ещё не означает ответ ``action=query``: MediaWiki так же
            # возвращает JSON с ``error``. Такой ответ не может подтверждать отсутствие
            # статьи, иначе временный отказ становился ``empty`` на целую неделю.
            if isinstance(json_map(json_map(payload).get("query")).get("pages"), list):
                with lock:
                    answers.append((part, payload))

    parts = [names[at : at + _EXLIMIT] for at in range(0, len(names), _EXLIMIT)]
    # The shared client gives Wikimedia five request lanes.  A full home screen needs
    # seven batches, so its queued batches need a second source interval plus one
    # closing interval rather than being called incomplete at the deadline boundary.
    rounds = (len(parts) + _LANES - 1) // _LANES
    deadline = time.monotonic() + timeout * (rounds + 1)
    wave = [threading.Thread(target=ask, args=(part,), daemon=True) for part in parts]
    for thread in wave:
        thread.start()
    answers = closed_wave(wave, deadline, lambda: list(answers))
    if not answers:
        raise OSError("Википедия не ответила ни на один запрос")
    heard = {name for part, _payload in answers for name in part}
    answered = {
        key for key in wanted if scheduled[key] and all(name in heard for name in scheduled[key])
    }
    payload = _merged([reply for _part, reply in answers])
    complete = {key for key in answered if all(name in heard for name in candidates[key])}
    return candidates, payload, answered, complete
