"""Вторая волна за статьями на языке продукта; зовёт добор справки к меню."""

from __future__ import annotations

import contextlib
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any

from torrcast.adapters.wiki.closed_wave import closed_wave
from torrcast.adapters.wiki.endpoints import WIKI_PATH
from torrcast.adapters.wiki.wiki_host import wiki_host
from torrcast.domain.facts.blurb_outcome import ABSENT, BLANK, PARSED
from torrcast.domain.facts.extract_params import extract_params
from torrcast.domain.facts.settings import _EXLIMIT
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article, _merged
from torrcast.ports.journal.slot import journal
from torrcast.ports.json_client import JsonClient
from torrcast.ports.json_value import JsonValue

#: Картина в справке названа именем и годом - тем же ключом, что и во всём доборе.
Key = tuple[str, int | None]


def wiki_translated(
    client: JsonClient,
    found: Sequence[Key],
    linked: Mapping[Key, str],
    language: str,
    timeout: float,
) -> tuple[dict[Key, str], dict[Key, str]]:
    """Описания тех же картин из Википедии языка продукта и исход разбора у каждой.

    Спрашиваются НЕ имена картин, а межъязыковые заголовки уже найденных статей
    (:func:`~torrcast.domain.facts.linked_title.linked_title`). Причина простая: имена
    картин приезжают с русскоязычных трекеров, и английская Википедия про «Юную
    революционерку Утэну» не знает ничего, а про «Revolutionary Girl Utena» знает всё.
    Кто картина такая, уже решено гейтами первой волны, и решать это заново тут нечем и
    незачем: межъязыковая ссылка ведёт к ТОЙ ЖЕ статье по построению.

    🔴 Нет ссылки - справки нет вовсе (:data:`ABSENT`): остаются имя, год и оценка. Взять
    описание из русской статьи было бы подменой языка, а строка-оговорка рядом с ней -
    той же подменой, только с извинением.

    Второй ответ - исход у каждой картины, и он тремя различимыми словами, а не «пусто»
    на всё: см. :mod:`torrcast.domain.facts.blurb_outcome`.
    """
    names = [linked[key] for key in found if linked.get(key)]
    payload, asked, heard = _wave(client, names, language, timeout)
    hops, pages = wiki_pages(payload)
    about: dict[Key, str] = {}
    outcome: dict[Key, str] = {}
    for key in found:
        name = linked.get(key, "")
        if not name:
            outcome[key] = ABSENT
            continue
        page = _article(name, hops, pages)
        extract = str(page.get("extract") or "") if page is not None else ""
        outcome[key] = PARSED if extract else BLANK
        if extract:
            about[key] = extract
    _trace(language, outcome, asked, heard)
    return about, outcome


def _wave(
    client: JsonClient, names: list[str], language: str, timeout: float
) -> tuple[dict[str, Any], int, int]:
    """Пакетный запрос статей одной волной; сколько пакетов ушло и сколько вернулось.

    Волна, а не очередь: пакеты идут разом и закрываются общим дедлайном
    (:func:`closed_wave`) - тем же порядком, что и первая волна справки. Отказ тут не
    исключение: часть картин просто останется без описания, а показ справка ронять не
    вправе. Различить «сеть не ответила» и «разбор пуст» позволяет пара чисел в следе.
    """
    parts = [names[at : at + _EXLIMIT] for at in range(0, len(names), _EXLIMIT)]
    answers: list[Any] = []
    lock = threading.Lock()
    host = wiki_host(language)

    def ask(part: list[str]) -> None:
        with contextlib.suppress(Exception):
            answer = client.get(host, WIKI_PATH, extract_params(part), {}, timeout)
            with lock:
                answers.append(answer)

    deadline = time.monotonic() + timeout
    wave = [threading.Thread(target=ask, args=(part,), daemon=True) for part in parts]
    for thread in wave:
        thread.start()
    answers = closed_wave(wave, deadline, lambda: list(answers))
    return _merged(answers), len(parts), len(answers)


def _trace(language: str, outcome: Mapping[Key, str], asked: int, heard: int) -> None:
    """Исход разбора в след: доля пропавшей справки считается по этой записи.

    🔴 Считается она только тогда, когда исходы РАЗЛИЧИМЫ. «Статьи на этом языке нет» -
    честный итог и знаменателю не помеха; «статья есть, а описания нет»
    (:data:`~torrcast.domain.facts.blurb_outcome.BLANK`) - дефект, и он назван отдельно.
    Имена дефектных едут рядом с числом: доля говорит, сколько сломалось, а найти это
    можно только по имени.

    Пакеты названы числами тем же событием: волна, которой не ответила сеть, даёт те же
    пустые описания, что и сломанный разбор, и отличить одно от другого больше нечем.
    """
    if not outcome:
        return
    blank: list[JsonValue] = []
    for key in sorted(outcome, key=lambda named: named[0]):
        if outcome[key] == BLANK:
            blank.append(key[0])
    journal().mark(
        "справка: язык продукта",
        язык=language,
        разобрано=sum(1 for why in outcome.values() if why == PARSED),
        нет_статьи=sum(1 for why in outcome.values() if why == ABSENT),
        пусто=len(blank),
        пустые=blank,
        пакетов=asked,
        отвечено=heard,
    )
