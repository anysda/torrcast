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
from torrcast.ports.json_client import JsonClient


def wiki_extracts(
    client: JsonClient,
    wanted: list[tuple[str, int | None]],
    timeout: float,
    kinds: Mapping[tuple[str, int | None], str] | None = None,
) -> tuple[
    dict[tuple[str, int | None], list[str]],
    dict[str, Any],
    set[tuple[str, int | None]],
]:
    """Запросить кандидатов волной и назвать картины с полным ответом.

    Тип картины правит ПОРЯДОК кандидатов (:func:`titles_for`), а не их набор: в волну
    влезает не всё, и уточнение чужого типа впереди своего стоит места настоящей статьи.

    Имена ВСЕХ спрошенных картин едут в перебор каждой: имя соседа по вопросу - не
    кандидат, а чужой адрес, и отрезанный подзаголовок не вправе его занимать
    (:func:`titles_for`).
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
            payload = client.get(WIKI_HOST, WIKI_PATH, extract_params(part), {}, timeout)
            with lock:
                answers.append((part, payload))

    parts = [names[at : at + _EXLIMIT] for at in range(0, len(names), _EXLIMIT)]
    deadline = time.monotonic() + timeout
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
    return candidates, _merged([payload for _part, payload in answers]), answered
