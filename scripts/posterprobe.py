#!/usr/bin/env python3
"""Щуп картинок списка обзора: сколько плиток обещано и у скольких байты не доехали.

Стоит у той же двери, что и Home Assistant: ``POST /api/search`` за списком, а следом,
не отпуская его, ``GET /api/poster/<имя>`` за каждой обещанной картинкой - ровно так,
как их спрашивает браузер, дорисовывая плитки. Гадать тут не о чем: обещание - это поле
``poster`` в записи выдачи, а битая плитка - 404 на это самое имя.

🔴 Мерить одним числом «битых» нельзя, и это куплено ложной зеленью. Промах байтов
откладывает следующий поход за той же картиной (``hass.hit_posters._RETRY``), поэтому
следующий прогон показывает не битых, а МЕНЬШЕ ОБЕЩАНИЙ: имени такая картина уже не
получает, плитка молча уходит из списка, и прибор, глядящий только на 404, объявляет
это здоровьем. Поэтому щуп ведёт три числа за прогон и держит их вместе:

* ``обещано`` - записей, получивших имя картинки;
* ``битых`` - обещанных имён, ответивших не 200;
* ``отложено`` - картин, встреченных в выдаче ЭТОГО прогона, которым имя давали в
  каком-либо прошлом прогоне серии, а теперь не дали. Это и есть отложенный промах;
* ``на полке`` - битых плиток, чьи байты В ЭТОТ САМЫЙ МОМЕНТ лежат у моста на диске
  (``--shelf``). Число это разводит две породы битой плитки окончательно: байтов нет
  нигде - промахнулся поход в сеть; байты на полке есть, а дверь отвечает 404 - в сеть
  вообще ничего не промахивалось, потерян учёт, и чинится это не сроками и не сетью.

Отсюда и требование серии: один прогон различить эти два отказа не может в принципе -
отложенный промах виден только вторым прогоном о тех же картинах.

    python scripts/posterprobe.py --base http://127.0.0.1:8479 --runs 3
    python scripts/posterprobe.py --runs 3 --warm 1 --cold 'systemctl restart torrcast-ha'

``--cold`` выполняется перед каждым прогоном, и щуп ждёт, пока дверь снова ответит:
холодный прогон - это пустая полка и поднятый заново мост, а не просто повтор.

🔴 ``--warm`` тут обязателен, а не украшение: холодный прогон отложенного промаха не
видит НИКОГДА - карта промахов живёт в памяти моста и умирает вместе с ним. Отложенный
промах виден только тёплым проходом сразу за холодным, по тем же самым картинам.

🔴 И тёплый проход нужен НЕ ОДИН, а два: промах, случившийся в первом тёплом проходе,
откладывает картину только для следующего, и с ``--warm 1`` показать его нечем -
столбец «отложено» останется нулевым при любом числе битых. Меньше двух тёплых проходов
за холодным - это прибор, умеющий мерить лишь одну из двух пород отказа.

Инструмент разработчика: в устанавливаемый пакет не входит.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Final, NamedTuple

#: Всплеск запросов, каким список картинок спрашивает браузер: плитки едут разом.
_TILES: Final = 8
#: Сколько ждём одну картинку. Дверь отдаёт 404 сразу, так что срок тут не про терпение.
_TIMEOUT: Final = 30.0
#: Сколько ждём список: холодный поиск ходит по трекерам и бывает долгим.
_SEARCH_TIMEOUT: Final = 180.0
#: Сколько ждём дверь после подъёма моста, секунды.
_WAKE: Final = 60.0
#: Запросы всплеска. Восемь разных картин: у одной полки на всех промах не повторяется.
_QUERIES: Final = (
    "матрица",
    "интерстеллар",
    "бегущий по лезвию",
    "начало",
    "властелин колец",
    "гладиатор",
    "престиж",
    "терминатор",
)


class Picture(NamedTuple):
    """Картина выдачи: чем щуп отличает её от тёзки между прогонами."""

    title: str
    year: int | None
    kind: str


class Tally(NamedTuple):
    """Итог одного прогона: обещания, битые байты и отложенные промахи порознь."""

    records: int
    promised: int
    broken: int
    held: int
    shelved: int
    seconds: float
    slowest: float
    waited: float


def _post(base: str, path: str, body: dict[str, Any]) -> Any:
    """Ответ двери на команду; своих сроков у щупа два, и это не один и тот же срок."""
    request = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=_SEARCH_TIMEOUT) as answer:
        return json.loads(answer.read())


def _picture(record: dict[str, Any]) -> Picture:
    """Тождество картины по записи выдачи: тем же тройкой её знает и сам мост."""
    year = record.get("year")
    return Picture(
        str(record.get("title") or "").strip(),
        year if isinstance(year, int) and not isinstance(year, bool) else None,
        "tv" if record.get("kind") == "tv" else "movie",
    )


def _tile(base: str, name: str) -> tuple[bool, float]:
    """Дала ли дверь картинку и за сколько секунд.

    🔴 Секунды тут нужны и у БИТОЙ плитки, и это второй разделитель прибора. Дверь
    держит запрос картинки, которая ещё в пути (``hass.hit_posters._WAIT``), и отпускает
    его либо байтами, либо сроком. Значит битая плитка бывает двух разных пород: 404
    сразу - байты уже промахнулись и поход закончен; 404 через несколько секунд - байты
    ещё ехали, а ждать их перестали. Одним числом «битых» эти два отказа неразличимы, а
    чинятся они разным.
    """
    started = time.monotonic()
    address = base + "/api/poster/" + urllib.parse.quote(name, safe="")
    try:
        with urllib.request.urlopen(address, timeout=_TIMEOUT) as answer:
            body = answer.read()
    except (urllib.error.URLError, TimeoutError, OSError):
        return False, time.monotonic() - started
    return bool(body), time.monotonic() - started


def _shelved(shelf: str, name: str) -> bool:
    """Лежат ли байты этой картинки у моста на полке ПРЯМО СЕЙЧАС.

    🔴 Это и есть разделитель двух пород битой плитки, и он единственный работает по
    факту, а не по сроку. Полка именует файл отпечатком имени картинки
    (``hass.poster_shelf.PosterShelf._where``), тем же самым, какое уехало в выдачу, -
    значит по битому имени всегда можно спросить диск. Байтов нет нигде: промахнулся
    поход в сеть, и чинится это сроками, повторами и источниками. Байты на полке ЕСТЬ, а
    дверь отвечает 404: в сеть ничего не промахивалось вовсе, потерян учёт готового, и ни
    один срок такого не лечит. Щуп обязан стоять на том же узле, что и мост.
    """
    if not shelf:
        return False
    return (Path(shelf) / hashlib.sha256(name.encode("utf-8")).hexdigest()[:24]).exists()


class Burst(NamedTuple):
    """Итог одного всплеска плиток: битые, их байты на полке и края по секундам."""

    broken: int
    shelved: int
    slowest: float
    waited: float


def _burst(base: str, names: list[str], shelf: str) -> Burst:
    """Спросить пачку плиток разом и тут же сказать, что с битыми.

    Полка спрашивается СРАЗУ за отказом, а не в конце прогона: между тем и другим мост
    успевает и дописать байты, и вытеснить их, и ответ был бы уже о другом мгновении.
    """
    if not names:
        return Burst(0, 0, 0.0, 0.0)
    with ThreadPoolExecutor(max_workers=_TILES) as tiles:
        spent = list(tiles.map(lambda one: _tile(base, one), names))
    missed = [name for name, (ok, _) in zip(names, spent, strict=True) if not ok]
    return Burst(
        len(missed),
        sum(1 for name in missed if _shelved(shelf, name)),
        max([0.0, *[one for ok, one in spent if ok]]),
        max([0.0, *[one for ok, one in spent if not ok]]),
    )


def _named(rows: object) -> list[str]:
    """Имена картинок этой выдачи по порядку: обещание - это поле, а не догадка."""
    return [
        row["poster"]
        for row in (rows if isinstance(rows, list) else [])
        if isinstance(row, dict) and isinstance(row.get("poster"), str) and row["poster"]
    ]


def _run(
    base: str, queries: tuple[str, ...], named: set[Picture], shelf: str = "", after: bool = False
) -> Tally:
    """Один прогон: список за списком, и картинки каждого - сразу, всплеском.

    Картинки спрашиваются, не отпуская список: браузер рисует плитки тут же, и именно
    в это окно байты ещё едут. Ждать перед ними значило бы мерить полку, а не поход.

    🔴 ``after`` переносит все плитки прогона в один всплеск ПОСЛЕ всех поисков, и это не
    украшение, а способ сделать перемежающийся отказ повторимым. Поквартальное чтение
    прячет вытеснение: имя спрашивают через миг после того, как мост положил его
    готовым, и вытеснить его ещё не успели. Человек же возвращается к прошлому списку
    позже - к тому времени мост держит наготове уже другие картинки. Отказ от этого не
    становится другим, он становится ВИДИМЫМ каждый раз.
    """
    started = time.monotonic()
    records = promised = broken = held = shelved = 0
    slowest = waited = 0.0
    later: list[str] = []
    for query in queries:
        answer = _post(base, "/api/search", {"query": query})
        rows = answer.get("results") if isinstance(answer, dict) else None
        for record in rows if isinstance(rows, list) else []:
            if not isinstance(record, dict):
                continue
            records += 1
            name, about = record.get("poster"), _picture(record)
            if not isinstance(name, str) or not name:
                held += 1 if about in named else 0
                continue
            promised += 1
            named.add(about)
        names = _named(rows)
        if after:
            later.extend(names)
            continue
        got = _burst(base, names, shelf)
        broken, shelved = broken + got.broken, shelved + got.shelved
        slowest, waited = max(slowest, got.slowest), max(waited, got.waited)
    if after:
        got = _burst(base, later, shelf)
        broken, shelved = got.broken, got.shelved
        slowest, waited = got.slowest, got.waited
    spent_all = time.monotonic() - started
    return Tally(records, promised, broken, held, shelved, spent_all, slowest, waited)


def _wake(base: str) -> None:
    """Дождаться двери после подъёма моста: поднятие асинхронно и врёт готовностью."""
    deadline = time.monotonic() + _WAKE
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(base + "/api/state", timeout=5.0) as answer:
                if answer.status == 200:
                    return
        except (urllib.error.URLError, TimeoutError, OSError):
            time.sleep(1.0)
    raise SystemExit(f"дверь {base} не ответила за {_WAKE:.0f} с")


def main() -> int:
    """Серия прогонов таблицей; битые байты и отложенные промахи названы порознь."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8479", help="дверь моста")
    parser.add_argument("--runs", type=int, default=3, help="сколько прогонов в серии")
    parser.add_argument("--cold", default="", help="команда перед каждым холодным прогоном")
    parser.add_argument("--warm", type=int, default=0, help="тёплых проходов за каждым холодным")
    parser.add_argument("--queries", nargs="*", default=list(_QUERIES), help="запросы всплеска")
    parser.add_argument("--shelf", default="", help="полка постеров моста, если щуп на том же узле")
    parser.add_argument("--after", action="store_true", help="плитки одним всплеском после поисков")
    chosen = parser.parse_args()
    queries = tuple(chosen.queries)
    rows: list[Tally] = []
    print(
        "прогон  вид      находок  обещано  битых  отложено  на полке"
        "  секунд  дольшая плитка  дольшая битая"
    )
    for number in range(1, chosen.runs + 1):
        # Карта обещанного живёт ровно столько же, сколько карта промахов в мосту: с
        # холодным подъёмом обе начинаются заново, и отложенное считать не с чем.
        named: set[Picture] = set()
        for step in range(chosen.warm + 1):
            if chosen.cold and not step:
                subprocess.run(chosen.cold, shell=True, check=True)
                _wake(chosen.base)
            tally = _run(chosen.base, queries, named, chosen.shelf, chosen.after)
            rows.append(tally)
            kind = "холодный" if chosen.cold and not step else "тёплый  "
            print(
                f"{number:>6}  {kind}  {tally.records:>7}  {tally.promised:>7}"
                f"  {tally.broken:>5}  {tally.held:>8}  {tally.shelved:>8}"
                f"  {tally.seconds:>6.1f}"
                f"  {tally.slowest:>14.1f}  {tally.waited:>13.1f}"
            )
            sys.stdout.flush()
    bad = sum(one.broken for one in rows)
    late = sum(one.held for one in rows)
    kept = sum(one.shelved for one in rows)
    print(f"итого: битых {bad}, отложенных {late}, из битых лежало на полке {kept}")
    return 1 if bad or late else 0


if __name__ == "__main__":
    raise SystemExit(main())
