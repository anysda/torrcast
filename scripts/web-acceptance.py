#!/usr/bin/env python3
"""Приёмочная проверка веб-показа: каждый пункт - число, а не «открылось».

Инструмент разработчика: headless Chromium (playwright), в устанавливаемый пакет не
входит и в зависимости продукта не входит - как ``scripts/kinshelfprobe.py`` и
``scripts/recodebench.py``. Ставится отдельно, рядом с браузером, и зовётся против
живого запущенного экземпляра torrcast::

    PLAYWRIGHT_BROWSERS_PATH=... python3 \
        scripts/web-acceptance.py --base http://ХОСТ:ПОРТ

Пункты 12-13 и 15-16 не ходят через браузер вовсе, им хватает выдачи; пункт 14 обязан
запускаться там, где лежит дерево ``torrcast`` (``--repo``), а не там, где стоит браузер.

Проверка обязана называть, ЧЕМ именно она недовольна - конкретный запрос, конкретное
число, конкретный отсутствующий узел DOM. Ни один пункт не пропускается молча: у
каждого либо оценка, либо явная пометка «заблокирован» с причиной.

🔴 Полоса упаковки на запущенном экземпляре ОДНА: второй читатель уводит головку у
первого. Показ (пункты 4, 6-11, 20) поэтому НЕ запускается сам по себе - только по
``--play``, и без него проверка доказывает выключение отчётом ``/api/state``, а не
имитацией. ``allow_play`` - единственная дверь к показу для всего прибора: и клик, и
слепой Enter по фокусу, вставшему на «Играть» (пункт 11), проходят один и тот же
тормоз. Пункты 9-10 (Chromecast) читают состояние приёмника через продуктовое
``/api/state``, а не вторым ``pychromecast``: второй сендер к тому же приёмнику неотличим
от первого для приёмника и рвёт чужой показ
(:class:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver`,
докстрока класса) - наблюдать чужой каст безопасно чем угодно, кроме этого.

Контракт DOM (``data-tc-*``) - страница вешает ``data-tc-tile``, ``data-tc-card``,
``data-tc-card-description``, ``data-tc-card-rating``, ``data-tc-play`` и
``data-tc-episode``, кнопки над полкой - ``data-tc-shelf-step`` (``1`` и ``-1``), плеер -
``data-tc-audio-option`` и ``data-tc-next-episode``.
Заголовки полок и кнопки проверка ищет по ТЕКСТУ из ``/api/phrases`` - это переживёт
смену разметки, а не переживёт смену каталога.

⚠️ Пункт 13 - грепом, а не разбором AST: однословный литерал (``'Play'``) от ключа
каталога не отличить простым грепом по кавычкам. Это названный предел точности этой
проверки, а не дыра, которую прячут.

Пункты 28-31 - карточка глазами человека: секунды от клика до обложки, имени и описания
в DOM и число ``GET /api/card`` самой страницы, а не отклик сервера. 31 и 28 идут первыми,
на свежей странице: пункты после них водят по полкам и греют плитки. ``--only 28,31``
гоняет только названные пункты.
"""

from __future__ import annotations

import argparse
import contextlib
import itertools
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Три полки главной страницы - ключи каталога `torrcast/domain/catalogs/web/en.py`.
_SHELF_KEYS: Final = (
    "web.shelf.continue_watching",
    "web.shelf.new",
    "web.shelf.popular",
)

#: Те же десять франшиз, что и в `scripts/kinshelfprobe.py` - число обязано
#: сходиться с тем щупом: расхождение само по себе находка, а не шум.
#: Десять франшиз, названные ТАК ЖЕ, как их называет полка родни. Именем франшизы, а
#: не конкретной части: «Миссия невыполнима 2» продукт отвергает по делу («в франшизе 9
#: картин, номера 2 среди них нет»), и мерился бы этим не охват Wikidata, а моя догадка
#: о нумерации. Зритель набирает ровно название, а какую часть открыть - решает продукт.
_FRANCHISE_TITLES: Final = (
    "Крепкий орешек",
    "Гарри Поттер",
    "Пираты Карибского моря",
    "Матрица",
    "Чужой",
    "Терминатор",
    "Форсаж",
    "Миссия невыполнима",
    "Джон Уик",
    "Шрек",
)
#: Сколько ждать доборные части карточки (справка, серии, родня): продукт отвечает
#: сразу и досылает их фоном, помечая недоехавшее заголовком ``X-Torrcast-Partial``.
#: Окно §9: столько плиток полки видно человеку, и по ним же меряются обложки и мусор.
_SHELF_WINDOW: Final = 30
#: Планка §9 по обложкам: «не ниже потолка выдачи (60%)».
_POSTER_BAR: Final = 0.6
#: Чем плитка называет себя НЕ кино и не сериалом. Приметы скрипта, а не продукта, и
#: потому короткие: сюда попадает лишь то, что в титуле картины не стоит никогда -
#: платформа, сцен-метка перевыпуска, формат звука, паки книг и манги по номерам томов,
#: трансляции спорта. По живому замеру «Mortal Kombat 1 ... PC | RePack» приезжал плиткой
#: фильма; следом за ним тем же путём проезжали паки манги («... v01-10», «... 001-011» -
#: подряд идущие номера томов с ведущим нулём отличают паковку от года или части фильма)
#: и эфиры спортивных передач («Match Of The Day», «All Elite Wrestling ...») - ни один из
#: остальных пунктов на титул полки не смотрит, увидеть это может только этот пункт.
_JUNK_RE: Final = re.compile(
    r"(?i)(?<![a-z])(repack|gog-rip|steam-rip|flac|mp3|ape|epub|fb2|djvu|apk|"
    r"artbook|artbuk|wallpapers?)(?![a-z])|\|\s*pc\b|\bpc\s*[|]"
    r"|(?<![a-z0-9])v?0\d{1,3}\s*-\s*0?\d{1,3}(?![a-z0-9])"
    r"|\b(all elite wrestling|wwe raw|wwe smackdown|match of the day|ufc \d+)\b"
)

#: Картина, у которой латинское имя точно есть и известно нам заранее (франшиза
#: «Матрица» → «The Matrix») - опора отрицательной пробы §19: экран обязан показать
#: латинское имя, раз оно записано, а не оставить кириллицу от запроса.
_LATIN_KNOWN_TITLE: Final = "Матрица"
#: Кириллица - единственная примета, которую ищет пункт 19. Диапазон покрывает и
#: основной алфавит, и расширение (Ё, Ѐ и т.п.).
_CYRILLIC_RE: Final = re.compile(r"[\u0400-\u04ff]")

_PARTIAL_WAIT: Final = 30.0
#: Сериал для пункта 7. Карточка фильма из пункта 3 серий не содержит по устройству
#: продукта, и судить по ней список серий - вечная краснота независимо от кода. По
#: живому замеру у этого имени разбирается первый сезон целиком, 7 серий.
#: Фильм приёмки: его ищет пункт 2, его же карточку открывают пункты 3 и 6.
_MOVIE_TITLE: Final = "Интерстеллар"
_SERIES_TITLE: Final = "Во все тяжкие"
#: Сколько ждать тело карточки, открытой кликом: карточка едет по сети, и нажимать
#: стрелки по скелету значит мерить скорость сети, а не навигацию. По живому замеру у
#: сериала разбор раздачи в TorrServer доезжает за 25-30 с, у фильма - сразу.
_CARD_READY_WAIT: Final = 45000.0
#: Сколько ждать первый кадр после «Играть». Продукт успевает найти раздачу, снять
#: метаданные роя и упаковать первые куски: по живому замеру это заняло 10 с до
#: `readyState 4`, порог взят с запасом на холодный рой.
_PLAY_START_WAIT: Final = 90000.0
#: Плитка, которую можно открыть. Пока полка не доехала, страница рисует СКЕЛЕТЫ тем же
#: `data-tc-tile`, и первый узел в DOM обычно как раз скелет: у него нет ни обработчика,
#: ни фокуса, и клик по нему не делает ничего (по живому замеру - 14 скелетов).
_LIVE_TILE: Final = "[data-tc-tile][data-tc-focusable]"

#: Число внутри строки рейтинга: «IMDb 8.7» - оценка есть, «IMDb» без цифры - нет.
_NUMBER_RE: Final = re.compile(r"\d+[.,]?\d*")

#: Строковый литерал в кавычках: одинарных или двойных, с экранированием внутри.
_STRING_RE: Final = re.compile(r"""(['"])((?:\\.|(?!\1).)*)\1""")
#: Ключ каталога: `web.header.seat`, `web.detail.releases` - точки, строчные буквы.
_KEY_RE: Final = re.compile(r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+$")
#: Список css-классов через пробел: `tc-header tc-safe` - не текст человеку.
_CLASS_LIST_RE: Final = re.compile(r"^[a-z][a-z0-9-]*(?:\s[a-z][a-z0-9-]*)*$")
#: Вызов `TC.say('key', ...)` - какой ключ каталога спрашивает страница.
_SAY_KEY_RE: Final = re.compile(r"""\.say\(\s*['"]([\w.]+)['"]""")
#: CSS-свойство `content:` (не `justify-content:`) - единственное место, откуда CSS
#: способен показать человеку текст.
_CONTENT_PROP_RE: Final = re.compile(r"""(?<![\w-])content\s*:\s*(['"])((?:\\.|(?!\1).)*)\1""")
#: Селектор (`.tc-tile-art-img, .tc-tile-noart`) и css-значение (`calc(100% + 1rem)`):
#: служебные токены с пробелом внутри, которые иначе идут за текст человеку. Обе
#: приметы узкие нарочно - строка человека не начинается с точки и не зовётся `calc(`.
_SELECTOR_RE: Final = re.compile(r"^[.#][a-z][\w-]*(?:\s*,\s*[.#][a-z][\w-]*)*$")
_CALC_RE: Final = re.compile(r"^calc\(.*\)$")
#: Что страница грузит сама. Список файлов пункт 13 берёт из её разметки, а не из
#: своего перечня имён: перечень внутри пункта устаревает молча, и новый скрипт
#: `index.html` выпадает из-под сторожа, ничего никому не сказав.
_PAGE_SCRIPT_RE: Final = re.compile(r"""<script[^>]*\bsrc=["'](/static/[^"']+\.js)["']""")
_PAGE_STYLE_RE: Final = re.compile(r"""<link[^>]*\bhref=["'](/static/[^"']+\.css)["']""")
#: Чужое добро, которое пункт 13 не судит: минифицированный бандл плеера и шрифтовой
#: css. Литералы там не наши, и правит их не эта репа.
_VENDORED_RE: Final = re.compile(r"\.min\.js$|^/static/fonts/")


@dataclass(slots=True)
class Result:
    """Итог одного пункта §11: число и слово, чем именно недоволен скрипт."""

    number: int
    name: str
    ok: bool
    blocked: str | None
    detail: str


@dataclass(slots=True)
class Ctx:
    """Общее для проверок: адрес экземпляра, открытая страница, флаги и словарь надписей."""

    base: str
    page: Any
    allow_play: bool
    shots: Path
    english: dict[str, str]


def _get(url: str, timeout: float = 10.0) -> tuple[int, bytes]:
    """GET чистым ``urllib``: скрипт не тянет ``requests`` в свой окружающий venv.

    Код 0 - «ответа нет вовсе», и тело тогда несёт слова о причине, включая
    отпущенное время: «молчит дольше N секунд» и «сказал 404» - разные
    приговоры, и сливать их в одно «скрипт упал» нельзя. ``urlopen`` по
    истечении времени поднимает голый ``TimeoutError`` (он же
    ``socket.timeout``) МИМО ``URLError``: до этой правки он улетал в
    ``_guarded`` и ронял пункт без единого числа, а в ``main()`` (предварительный
    опрос ``/api/phrases``) - весь прогон целиком.
    """
    request = urllib.request.Request(url, headers={"User-Agent": "web-acceptance"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except TimeoutError:
        return 0, f"нет ответа за {timeout:.0f} с (таймаут)".encode()
    except urllib.error.URLError as error:
        return 0, str(error.reason).encode("utf-8")
    except OSError as error:
        return 0, f"сбой транспорта: {error}".encode()


def _shelf_tile_counts(payload: Any) -> dict[str, int]:
    """Число плиток на полку из `/api/shelves`, в двух правдоподобных формах ответа."""
    counts: dict[str, int] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            if isinstance(value, list):
                counts[str(key)] = len(value)
            elif isinstance(value, dict) and isinstance(value.get("tiles"), list):
                counts[str(key)] = len(value["tiles"])
    elif isinstance(payload, list):
        for entry in payload:
            if isinstance(entry, dict):
                key = str(entry.get("key") or entry.get("title") or len(counts))
                tiles = entry.get("tiles") or entry.get("items") or []
                if isinstance(tiles, list):
                    counts[key] = len(tiles)
    return counts


def _is_prose(text: str) -> bool:
    """Похоже ли содержимое литерала на текст человеку, а не на служебный токен.

    Пробел по КРАЯМ примету не даёт: `' is-active'` - склейка с классом (`className +=`),
    а не фраза. Пробел внутри строки тем не менее остаётся приметой, поэтому обрезка
    идёт только перед сверкой со служебными формами, а не перед сверкой на пробел:
    иначе `'Play '` перестала бы считаться текстом человеку.
    """
    if not any(ch.isalpha() for ch in text):
        return False
    if _KEY_RE.match(text):
        return False
    if " " not in text:
        return False
    token = text.strip()
    if _SELECTOR_RE.match(token) or _CALC_RE.match(token):
        return False
    return not _CLASS_LIST_RE.match(token)


def _post(url: str, body: dict[str, Any], timeout: float = 30.0) -> tuple[int, bytes]:
    """POST с телом-словарём; коды 4xx возвращаются, а не поднимаются исключением."""
    data = json.dumps(body).encode()
    request = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as answer:
            return int(answer.status), answer.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        return 0, str(exc).encode()


def _card_of(base: str, title: str) -> dict[str, Any]:
    """Карточка картины тем же путём, что и у страницы: поиск даёт ключ, ключ - карточку.

    Доборные части (справка, серии, родня) приезжают фоном, и пока они в пути, продукт
    помечает ответ заголовком ``X-Torrcast-Partial``. Ждать по нему - единственный
    честный способ: спросить один раз и объявить пусто значит замерить скорость сети.
    """
    code, body = _post(base + "/api/search", {"query": title})
    if code != 200:
        detail = ""
        with contextlib.suppress(json.JSONDecodeError):
            detail = str(json.loads(body).get("error", ""))[:120]
        return {"_error": f"POST /api/search -> {code} {detail}".rstrip()}
    try:
        results = json.loads(body).get("results") or []
    except json.JSONDecodeError as exc:
        return {"_error": f"выдача поиска не JSON: {exc}"}
    if not results:
        return {"_error": "поиск не дал ни одной картины"}
    # Открывать надо ту картину, которую продукт САМ назвал лучшим совпадением
    # (`default` в выдаче, «Лучшее совпадение» на плитке), а не первую подряд. По
    # «Пиратам Карибского моря» первой приезжает «Фильм о фильме», и родни у него нет
    # никакой - замер франшизы вышел бы замером порядка выдачи, а не полки.
    chosen = next((row for row in results if row.get("default")), results[0])
    key = urllib.parse.quote(str(chosen.get("key", "")))
    query = urllib.parse.quote(title)
    deadline = time.monotonic() + _PARTIAL_WAIT
    while True:
        request = urllib.request.Request(f"{base}/api/card/{key}?query={query}")
        try:
            with urllib.request.urlopen(request, timeout=30.0) as answer:
                partial = answer.headers.get("X-Torrcast-Partial")
                payload = json.loads(answer.read())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            return {"_error": f"GET /api/card/ -> {exc}"}
        if not partial or time.monotonic() >= deadline:
            return dict(payload) if isinstance(payload, dict) else {"_error": "карточка не словарь"}
        time.sleep(1.0)


#: Главная должна быстро показать, что выдача ещё собирается: скелеты и слово
#: ``Loading_`` не требуют ни сети источников, ни готовой полки. 10 с - потолок
#: интерфейса, снятый на холодном стенде: там оба были видны к 6-й секунде.
_HOME_LOADING_WAIT: Final = 10.0
#: На том же холодном стенде настоящие 60 плиток приехали на 42-й секунде. 60 с
#: оставляет запас на холодный источник, но не превращает отсутствие выдачи в ожидание
#: без конца. Это отдельная мера от обещания «загружаем» выше.
_HOME_TILES_WAIT: Final = 60.0


def _home_loading(ctx: Ctx) -> bool:
    """Одновременно ли видны обещанные на время сборки скелет и слово загрузки."""
    loading = ctx.english.get("web.shelf.loading", "")
    return bool(
        loading
        and ctx.page.locator(".tc-tile-skeleton").count() > 0
        and ctx.page.locator(".tc-tile-skeleton").first.is_visible()
        and ctx.page.get_by_text(loading, exact=True).count() > 0
        and ctx.page.get_by_text(loading, exact=True).first.is_visible()
    )


def check_1_home(ctx: Ctx) -> Result:
    """Главная сверяет «Продолжить» с историей, а две полки выдачи - с API."""
    code, _ = _get(ctx.base + "/")
    began = time.monotonic()
    # `load` может наступить уже ПОСЛЕ быстрого ответа полок и стереть короткую,
    # но честно показанную заглушку из наблюдения. Начинаем с первого байта страницы:
    # оба потолка всё равно отмеряются ниже своими ожиданиями.
    ctx.page.goto(ctx.base + "/", wait_until="commit", timeout=15000)
    # Первое обещание человеку - не готовая выдача, а честная заглушка. Полки могут
    # собираться десятки секунд, но скелет и ``Loading_`` обязаны появиться к отдельному
    # названному потолку, иначе пустой экран маскируется более долгим ожиданием плиток.
    # Второе обещание - настоящая выдача. Ждём её состава, а не единственной живой
    # плитки: один случайный ответ не делает обе полки пригодными человеку. Обе меры
    # идут одновременно: на тёплой выдаче, успевшей до первого кадра, ожидания нет и
    # заглушку зрителю показывать незачем; на долгой - к 10 с уже обязана быть заглушка.
    loading_at: float | None = None
    counts: dict[str, int] = {}
    shelves_code = 0
    shelves_detail = "GET /api/shelves не спросили"
    tiles_at: float | None = None
    next_shelves = began
    while time.monotonic() - began < _HOME_TILES_WAIT:
        now = time.monotonic()
        if loading_at is None and now - began < _HOME_LOADING_WAIT and _home_loading(ctx):
            loading_at = now - began
        if now >= next_shelves:
            shelves_code, shelves_body = _get(ctx.base + "/api/shelves")
            shelves_detail = f"GET /api/shelves -> {shelves_code}"
            counts = {}
            if shelves_code == 200:
                try:
                    payload = json.loads(shelves_body)
                except json.JSONDecodeError as exc:
                    shelves_detail += f", тело не JSON: {exc}"
                else:
                    counts = _shelf_tile_counts(payload)
                    shelves_detail += f", полок {len(counts)}, плиток {counts}"
                    if set(counts) == {"fresh", "popular"} and all(
                        count >= 20 for count in counts.values()
                    ):
                        tiles_at = time.monotonic() - began
                        break
            next_shelves = now + 1.0
        ctx.page.wait_for_timeout(100)
    # Ответ API и замена скелетного тела происходят разными задачами браузера. После
    # готового снимка даём странице один короткий кадр дорисовать именно его, не
    # расширяя ни один из названных потолков ожидания выдачи.
    if tiles_at is not None:
        ctx.page.wait_for_timeout(300)
    found: list[tuple[str, int]] = []
    for key in _SHELF_KEYS[1:]:
        text = ctx.english.get(key, "")
        count = ctx.page.get_by_text(text, exact=True).count() if text else 0
        found.append((key, count))
    continue_text = ctx.english.get(_SHELF_KEYS[0], "")
    continue_shelf = ctx.page.get_by_text(continue_text, exact=True).locator(
        "xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' tc-shelf ')][1]"
    )
    continue_seen = continue_shelf.count() if continue_text else 0
    continue_tiles = continue_shelf.locator("[data-tc-tile]").count()
    history_code, history_body = _get(ctx.base + "/api/history")
    history_count: int | None = None
    history_detail = f"GET /api/history -> {history_code}"
    if history_code == 200:
        try:
            history = json.loads(history_body)
        except json.JSONDecodeError as exc:
            history_detail += f", тело не JSON: {exc}"
        else:
            items = history.get("items") if isinstance(history, dict) else None
            if isinstance(items, list):
                history_count = len(items)
                history_detail += f", записей {history_count}"
            else:
                history_detail += ", items не список"
    tiles_ok = tiles_at is not None
    loading_ok = loading_at is not None or (tiles_at is not None and tiles_at <= _HOME_LOADING_WAIT)
    history_ok = history_count is not None and (
        (history_count == 0 and continue_seen == 0)
        or (history_count > 0 and continue_seen == 1 and continue_tiles == history_count)
    )
    basics_seen = sum(1 for _, count in found if count > 0)
    ok = code == 200 and loading_ok and basics_seen == 2 and history_ok and tiles_ok
    by_key = ", ".join(f"{k.rsplit('.', 1)[-1]}={c}" for k, c in found)
    loading_detail = (
        f"скелет и Loading_ за {loading_at:.1f} с (потолок {_HOME_LOADING_WAIT:.0f} с)"
        if loading_at is not None
        else (
            f"готовая выдача за {tiles_at:.1f} с, заглушка не успела понадобиться"
            if tiles_at is not None and tiles_at <= _HOME_LOADING_WAIT
            else f"скелет и Loading_ не видны за {_HOME_LOADING_WAIT:.0f} с"
        )
    )
    tiles_detail = (
        f"настоящие плитки за {tiles_at:.1f} с (потолок {_HOME_TILES_WAIT:.0f} с)"
        if tiles_at is not None
        else f"настоящие плитки не собрались за {_HOME_TILES_WAIT:.0f} с"
    )
    detail = (
        f"GET / -> {code}; {loading_detail}; {tiles_detail}; "
        f"полки выдачи в DOM по тексту {basics_seen}/2 ({by_key}); "
        f"continue_watching={continue_seen}, плиток {continue_tiles}; {history_detail}; "
        f"{shelves_detail}"
    )
    return Result(1, "Главная", ok, None, detail)


#: Щупы полок для пунктов 17 и 23-27, ставятся на страницу ПОСЛЕ загрузки
#: (`_open_shelves`). Строка - родитель живой плитки, место - «полка:плитка» по порядку
#: в DOM: имя класса строки пунктам не нужно.
_SHELF_JS: Final = """
() => {
  const LIVE = '[data-tc-tile][data-tc-focusable]';
  const box = (el) => el.getBoundingClientRect();
  const mid = (el) => { const b = box(el); return b.left + b.width / 2; };
  const lit = () => document.querySelector('.is-lit');
  const S = {
    rows: () => [...new Set([...document.querySelectorAll(LIVE)].map((t) => t.parentElement))]
      .filter((r) => r.offsetParent !== null),
    show(r) { S.rows()[r].scrollIntoView({ block: 'center', behavior: 'instant' }); },
    where(el) {
      if (!el || el === document.body) return '-';
      const r = S.rows().indexOf(el.parentElement);
      if (r < 0 || !el.matches(LIVE)) return el.tagName.toLowerCase();
      return r + ':' + [...el.parentElement.children].indexOf(el);
    },
    now: () => ({ focus: S.where(document.activeElement), lit: S.where(lit()) }),
    lift(r, top) { window.scrollBy({ top: box(S.rows()[r]).top - top, behavior: 'instant' }); },
    park(r) {
      const most = document.documentElement.scrollHeight - innerHeight;
      const want = Math.min(scrollY + box(S.rows()[r]).top - 120, most - 80);
      window.scrollTo({ top: Math.max(0, want), behavior: 'instant' });
      return most - scrollY;
    },
    point(r, i) {
      const b = box(S.rows()[r].children[i]);
      return { x: b.left + b.width / 2, y: b.top + b.height / 3 };
    },
    under(x, y) {
      const e = document.elementFromPoint(x, y);
      return S.where(e && e.closest(LIVE));
    },
    pose: () => [scrollY, ...S.rows().map((r) => r.scrollLeft),
      ...[...document.querySelectorAll(LIVE)].slice(0, 60).map((t) => box(t).left)].join(','),
    boxes: () => [...[...document.querySelectorAll(LIVE)].slice(0, 60), ...S.rows()]
      .map((el) => { const b = box(el); return [b.left, b.top, b.width, b.height]; }),
    ring() {
      const f = lit() && lit().querySelector('.tc-tile-frame');
      if (!f) return false;
      const s = getComputedStyle(f);
      return s.outlineStyle !== 'none' && parseFloat(s.outlineWidth) > 0;
    },
    expect(way) {
      const from = lit() || document.activeElement;
      const rows = S.rows();
      const r = from ? rows.indexOf(from.parentElement) : -1;
      if (r < 0) return { from: S.where(from), place: '?' };
      const kids = [...rows[r].children];
      const i = kids.indexOf(from);
      const here = r + ':' + i;
      if (way === 'left' || way === 'right') {
        const j = Math.min(kids.length - 1, Math.max(0, i + (way === 'left' ? -1 : 1)));
        return { from: here, place: r + ':' + j };
      }
      const t = r + (way === 'down' ? 1 : -1);
      // Под нижней полкой идти некуда - стрелка стоит; над верхней - ближайшее помеченное
      // выше неё (поле поиска), а нет его - тоже стоит.
      if (t >= rows.length) return { from: here, place: here };
      if (t < 0) {
        const top = box(from).top;
        const above = [...document.querySelectorAll('[data-tc-focusable]')]
          .filter((el) => !el.matches(LIVE) && el.offsetParent !== null
            && box(el).bottom <= top + 1)
          .sort((a, b) => box(b).bottom - box(a).bottom);
        return { from: here, place: above.length ? S.where(above[0]) : here };
      }
      const x = mid(from);
      const next = [...rows[t].children];
      let j = 0;
      next.forEach((k, n) => { if (Math.abs(mid(k) - x) < Math.abs(mid(next[j]) - x)) j = n; });
      return { from: r + ':' + i, place: t + ':' + j };
    },
    overflow: () => S.rows().findIndex((r) => r.scrollWidth > r.clientWidth + 1),
    step(r, way) {
      const row = S.rows()[r];
      const kids = [...row.children];
      const b = box(row);
      const end = way > 0 ? box(kids[kids.length - 1]).right <= b.right + 0.5
        : box(kids[0]).left >= b.left - 0.5;
      const btn = row.parentElement.querySelector('[data-tc-shelf-step="' + way + '"]');
      if (!btn) return { end, x: null, y: null, off: true };
      const k = box(btn);
      return { end, x: k.left + k.width / 2, y: k.top + k.height / 2, off: btn.disabled };
    },
    bars() {
      const on = lit();
      return S.rows().map((row) => {
        const out = { sh: row.scrollHeight, ch: row.clientHeight,
          vbar: row.offsetWidth - row.clientWidth, hbar: row.offsetHeight - row.clientHeight,
          lit: false, fits: true, capbar: 0, lines: 0 };
        if (!on || on.parentElement !== row) return out;
        const frame = on.querySelector('.tc-tile-frame');
        const cap = on.querySelector('.tc-tile-cap');
        const text = cap && cap.querySelector('.tc-caption');
        const ring = frame ? parseFloat(getComputedStyle(frame).outlineWidth) || 0 : 0;
        const top = box(row).top + row.clientTop;
        out.lit = true;
        out.fits = box(frame || on).top - ring >= top - 0.5
          && box(on).bottom <= top + row.clientHeight + 0.5;
        if (cap) {
          out.capbar = Math.max(cap.offsetWidth - cap.clientWidth,
            cap.offsetHeight - cap.clientHeight);
        }
        if (text) {
          out.lines = Math.round(box(text).height / parseFloat(getComputedStyle(text).lineHeight));
        }
        return out;
      });
    },
  };
  window.__tcShelf = S;
}
"""
#: Стрелка → (сторона для щупа, значок для печати пути).
_ARROWS: Final = {
    "ArrowUp": ("up", "↑"),
    "ArrowDown": ("down", "↓"),
    "ArrowLeft": ("left", "←"),
    "ArrowRight": ("right", "→"),
}


def _open_shelves(page: Any, base: str) -> int:
    """Главная с доехавшими полками и поставленными щупами: сколько полок в 6+ плиток."""
    page.goto(base + "/", wait_until="load", timeout=15000)
    page.evaluate(_SHELF_JS)
    full = 0
    for _ in range(60):
        full = int(
            page.evaluate("() => __tcShelf.rows().filter((r) => r.children.length >= 6).length")
        )
        if full >= 2:
            break
        page.wait_for_timeout(500)
    page.wait_for_timeout(300)
    return full


def _settle(page: Any) -> None:
    """Дождаться, пока страница и полки встанут: плавная прокрутка едет сотни миллисекунд."""
    last = None
    for _ in range(40):
        page.wait_for_timeout(50)
        pose = page.evaluate("() => __tcShelf.pose()")
        if pose == last:
            return
        last = pose


def _hover(page: Any, row: int, index: int) -> None:
    """Навести указатель на плитку ОДНИМ движением из инертного угла, после того как всё встало."""
    page.mouse.move(5, 5)
    _settle(page)
    spot = page.evaluate("([r, i]) => __tcShelf.point(r, i)", [row, index])
    page.mouse.move(spot["x"], spot["y"])
    page.wait_for_timeout(300)


def _step_through(page: Any, row: int) -> tuple[bool, list[str]]:
    """Кнопками над строкой до последней плитки и обратно к первой; на краю кнопка гаснет."""
    page.evaluate("(r) => __tcShelf.show(r)", row)
    page.mouse.move(5, 5)
    _settle(page)
    notes: list[str] = []
    ok = True
    for way, mark, edge in ((1, "›", "последняя"), (-1, "‹", "первая")):
        clicks = 0
        state = page.evaluate("([r, w]) => __tcShelf.step(r, w)", [row, way])
        while not state["end"] and state["x"] is not None and not state["off"] and clicks < 40:
            page.mouse.click(state["x"], state["y"])
            clicks += 1
            _settle(page)
            state = page.evaluate("([r, w]) => __tcShelf.step(r, w)", [row, way])
        if state["x"] is None:
            notes.append(f"кнопки data-tc-shelf-step={way} НЕТ")
            ok = False
            continue
        ok = ok and bool(state["end"]) and bool(state["off"])
        shown = "целиком в строке" if state["end"] else "НЕ показана"
        notes.append(
            f"«{mark}» x{clicks}: {edge} плитка {shown}, "
            f"кнопка на краю {'погасла' if state['off'] else 'ГОРИТ'}"
        )
    return ok, notes


def check_17_wheel(ctx: Ctx) -> Result:
    """Мышь добирается до плиток за краем строки, хотя полосы прокрутки у строки нет.

    Путей у мыши три. Кнопки ``data-tc-shelf-step`` над строкой (``1`` - дальше, ``-1`` -
    назад) доводят до последней плитки и обратно к первой и на краю гаснут: на полке
    главной и в ряду «Ещё из этой серии» карточки (окно 1920, семь плиток франшизы там не
    влезают). Боковое колесо и Shift+колесо над полкой везут её вбок, не листая страницу.
    Вертикальное колесо над полкой - пункт 25: оно листает страницу.
    """
    page = ctx.page
    if _open_shelves(page, ctx.base) < 1:
        return Result(17, "Вбок", False, "полки не доехали", "на главной нет полки с плитками")
    row = int(page.evaluate("() => __tcShelf.overflow()"))
    if row < 0:
        detail = "ни одна полка не шире окна (scrollWidth <= clientWidth) - ехать вбок некуда"
        return Result(17, "Вбок", False, "нет переполненной полки", detail)
    ok, notes = _step_through(page, row)
    card = ctx.page.context.browser.new_page(viewport={"width": 1920, "height": 900})
    try:
        kin = _open_card(card) if _open_search(ctx, card, _FULL_SEARCH) > 0 else 0
        at = int(card.evaluate("() => __tcShelf.overflow()")) if kin else -1
        if at < 0:
            notes.append(f"карточка 1920: ряд серии ({kin} плиток) не переполнен, листать нечего")
            ok = False
        else:
            good, said = _step_through(card, at)
            ok = ok and good
            notes.append("карточка 1920, ряд серии: " + ", ".join(said))
    finally:
        card.close()
    for label, shift, dx, dy in (("боковое колесо", False, 300, 0), ("Shift+колесо", True, 0, 300)):
        page.evaluate(
            "(r) => { const row = __tcShelf.rows()[r]; row.style.scrollBehavior = 'auto';"
            " row.scrollLeft = 0; row.style.scrollBehavior = ''; }",
            row,
        )
        _hover(page, row, 1)
        before = page.evaluate("(r) => [scrollY, __tcShelf.rows()[r].scrollLeft]", row)
        if shift:
            page.keyboard.down("Shift")
        page.mouse.wheel(dx, dy)
        if shift:
            page.keyboard.up("Shift")
        _settle(page)
        after = page.evaluate("(r) => [scrollY, __tcShelf.rows()[r].scrollLeft]", row)
        ok = ok and after[1] > before[1] and after[0] == before[0]
        notes.append(
            f"{label}: scrollLeft {before[1]:.0f} -> {after[1]:.0f}, "
            f"scrollY {before[0]:.0f} -> {after[0]:.0f}"
        )
    return Result(17, "Вбок", ok, None, f"полка {row}: " + "; ".join(notes))


def check_23_hover(ctx: Ctx) -> Result:
    """Наведение не двигает ничего: ни одна плитка и ни одна полка не меняют размер и место.

    Выделение - обводка рамки плитки. Рост плитки и всей полки под указателем толкал
    соседей и полки ниже (замер 11-09-2026 на 1280: до 1121 px), и под неподвижной
    мышью оказывалась уже другая плитка.
    """
    page = ctx.page
    if _open_shelves(page, ctx.base) < 1:
        return Result(23, "Наведение", False, "полки не доехали", "на главной нет полки с плитками")
    page.evaluate("() => __tcShelf.lift(0, 200)")
    page.mouse.move(5, 5)
    _settle(page)
    before = page.evaluate("() => __tcShelf.boxes()")
    spot = page.evaluate("() => __tcShelf.point(0, 1)")
    page.mouse.move(spot["x"], spot["y"])
    page.wait_for_timeout(400)
    after = page.evaluate("() => __tcShelf.boxes()")
    now = page.evaluate("() => __tcShelf.now()")
    ring = bool(page.evaluate("() => __tcShelf.ring()"))
    if len(before) != len(after):
        detail = f"после наведения коробок {len(after)}, а до него {len(before)}"
        return Result(23, "Наведение", False, None, detail)
    shifts = [
        max(abs(a - b) for a, b in zip(old, new, strict=True))
        for old, new in zip(before, after, strict=True)
    ]
    moved = sum(1 for shift in shifts if shift > 0.5)
    worst = max(shifts, default=0.0)
    ok = moved == 0 and len(before) == len(after) and now["lit"] == "0:1" and ring
    detail = (
        f"наведение на плитку 0:1: сдвинулось {moved} из {len(shifts)} коробок (плитки и "
        f"полки), наибольший сдвиг {worst:.1f} px; горит {now['lit']}, "
        f"обводка рамки {'нарисована' if ring else 'НЕ нарисована'}"
    )
    return Result(23, "Наведение", ok, None, detail)


def _walk(page: Any, keys: list[str]) -> tuple[str, list[str]]:
    """Стрелки по одной; куда встать, щуп считает по раскладке ДО нажатия."""
    path: list[str] = []
    wrong: list[str] = []
    for number, key in enumerate(keys, 1):
        way, mark = _ARROWS[key]
        want = page.evaluate("(w) => __tcShelf.expect(w)", way)
        page.keyboard.press(key)
        _settle(page)
        got = page.evaluate("() => __tcShelf.now()")
        path.append(f"{mark}{got['focus']}")
        if got["focus"] != want["place"] or got["lit"] != want["place"]:
            wrong.append(
                f"шаг {number} {mark} от {want['from']}: ждали {want['place']}, "
                f"фокус {got['focus']}, горит {got['lit']}"
            )
    return " ".join(path), wrong


def check_24_arrows(ctx: Ctx) -> Result:
    """Стрелки: ←→ по плиткам своей полки, ↑↓ на соседнюю полку в ту же колонку экрана.

    Каждое нажатие - ровно один шаг, на краю полки стрелка стоит. Путь проходится дважды:
    от плитки, на которую указала мышь (фокус при этом ещё в поле поиска), и только
    клавишами от первой плитки. Где встать, пункт считает по раскладке до нажатия.
    """
    page = ctx.page
    if _open_shelves(page, ctx.base) < 2:
        return Result(24, "Стрелки", False, "меньше двух полок", "на главной меньше двух полок")
    page.evaluate("() => __tcShelf.lift(0, 150)")
    _hover(page, 0, 1)
    start = page.evaluate("() => __tcShelf.now()")
    mouse_keys = [
        "ArrowDown",
        *["ArrowRight"] * 3,
        "ArrowUp",
        *["ArrowLeft"] * 5,
        "ArrowDown",
        "ArrowUp",
    ]
    mouse_path, mouse_wrong = _walk(page, mouse_keys)
    page.mouse.move(5, 5)
    _open_shelves(page, ctx.base)
    page.evaluate("() => __tcShelf.lift(0, 150)")
    page.evaluate("() => __tcShelf.rows()[0].children[0].focus()")
    key_keys = ["ArrowLeft", *["ArrowRight"] * 9, "ArrowDown", "ArrowUp"]
    key_path, key_wrong = _walk(page, key_keys)
    wrong = mouse_wrong + key_wrong
    verdict = (
        f"неверных шагов {len(wrong)}: {'; '.join(wrong[:4])}"
        if wrong
        else f"все {len(mouse_keys) + len(key_keys)} шагов ровно на одну плитку или полку"
    )
    detail = (
        f"от мыши (горит {start['lit']}, фокус {start['focus']}): {mouse_path}; "
        f"только клавиши от 0:0: {key_path}; {verdict}"
    )
    return Result(24, "Стрелки", not wrong, None, detail)


def check_25_page_wheel(ctx: Ctx) -> Result:
    """Вертикальное колесо над любой полкой листает страницу и не трогает саму полку.

    Указатель стоит на плитке полки (она горит), колесо крутится вниз: ``scrollY``
    обязан вырасти, ``scrollLeft`` полки - остаться прежним. Полка ставится так, чтобы
    странице было куда ехать вниз, иначе пункт мерил бы край документа.
    """
    page = ctx.page
    if _open_shelves(page, ctx.base) < 1:
        return Result(25, "Колесо", False, "полки не доехали", "на главной нет полки с плитками")
    notes: list[str] = []
    ok = True
    for row in range(int(page.evaluate("() => __tcShelf.rows().length"))):
        room = float(page.evaluate("(r) => __tcShelf.park(r)", row))
        if room < 40:
            notes.append(f"полка {row}: странице некуда ехать вниз ({room:.0f} px)")
            ok = False
            continue
        _hover(page, row, 0)
        before = page.evaluate("(r) => [scrollY, __tcShelf.rows()[r].scrollLeft]", row)
        page.mouse.wheel(0, 300)
        _settle(page)
        after = page.evaluate("(r) => [scrollY, __tcShelf.rows()[r].scrollLeft]", row)
        ok = ok and after[0] > before[0] and after[1] == before[1]
        notes.append(
            f"полка {row}: scrollY {before[0]:.0f} -> {after[0]:.0f}, "
            f"scrollLeft {before[1]:.0f} -> {after[1]:.0f}"
        )
    return Result(25, "Колесо", ok, None, "; ".join(notes))


def _bars_sweep(page: Any, label: str, hovers: int) -> tuple[str, bool]:
    """Своя прокрутка и полосы каждой строки: в покое и под наведением на первые плитки."""
    page.mouse.move(5, 5)
    _settle(page)
    rest = page.evaluate("() => __tcShelf.bars()")
    lit: list[Any] = []
    sizes = page.evaluate("() => __tcShelf.rows().map((r) => r.children.length)")
    for row, size in enumerate(sizes):
        page.evaluate("(r) => __tcShelf.show(r)", row)
        for index in range(min(hovers, size)):
            _hover(page, row, index)
            lit.append(page.evaluate("() => __tcShelf.bars()")[row])
    everyone = [*rest, *lit]
    shown = [sample for sample in lit if sample["lit"]]
    rest_gap = max(sample["sh"] - sample["ch"] for sample in rest)
    lit_gap = max((sample["sh"] - sample["ch"] for sample in lit), default=0)
    vbar = max(sample["vbar"] for sample in everyone)
    hbar = max(sample["hbar"] for sample in everyone)
    capbar = max((sample["capbar"] for sample in shown), default=0)
    fits = sum(1 for sample in shown if sample["fits"])
    lines = sorted({sample["lines"] for sample in shown})
    pairs = " ".join(f"{sample['sh']}/{sample['ch']}" for sample in rest)
    ok = rest_gap == 0 and lit_gap == 0 and vbar == 0 and hbar == 0 and capbar == 0
    ok = ok and bool(shown) and fits == len(shown)
    note = (
        f"{label}: sh/ch покой {pairs}, sh-ch наведение до {lit_gap} ({len(shown)} наведений, "
        f"строк подписи {lines}), vbar {vbar}, hbar {hbar}, у подписи {capbar}, "
        f"плитка с обводкой вмещается {fits}/{len(shown)}"
    )
    return note, ok


#: Франшиза, у которой на стенде обе строки выдачи (12 находок) и ряд серии в 7 плиток.
_FULL_SEARCH: Final = "Гарри Поттер"
_HITS: Final = "[data-tc-group='search-results'][data-tc-focusable]"
#: Выдача, переставшая перерисовываться: та же первая находка и то же их число, что
#: и в прошлый опрос (иначе 0). Выдача доезжает частями и строится заново целиком, и
#: плитки, на которую навели до последней перестройки, в DOM уже нет.
_CALM_HITS_JS: Final = """
() => {
  const all = document.querySelectorAll("[data-tc-group='search-results'][data-tc-focusable]");
  const first = all[0];
  if (!first) return 0;
  const same = first.__tcSeen === true && window.__tcHits === all.length;
  first.__tcSeen = true;
  window.__tcHits = all.length;
  return same ? all.length : 0;
}
"""
_KIN_JS: Final = (
    "() => { const r = document.querySelector('.tc-detail-series-block .tc-row');"
    " return r ? r.children.length : 0; }"
)


def _open_search(ctx: Ctx, page: Any, title: str) -> int:
    """Выдача поиска, доехавшая и 3 с не менявшаяся; ответ - число находок (0 - не дождались)."""
    page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    placeholder = ctx.english.get("web.search.placeholder", "")
    field = page.get_by_placeholder(placeholder, exact=True) if placeholder else None
    if field is None or field.count() == 0:
        return 0
    field.first.fill(title)
    field.first.press("Enter")
    page.evaluate(_SHELF_JS)
    calm = 0
    found = 0
    for _ in range(120):
        page.wait_for_timeout(500)
        found = int(page.evaluate(_CALM_HITS_JS))
        calm = calm + 1 if found > 0 else 0
        if calm >= 6:
            return found
    return 0


def _open_card(page: Any) -> int:
    """С выдачи - в карточку первой находки; ответ - плиток в ряду серии (0 - ряда нет)."""
    page.locator(_HITS).first.click()
    kin = 0
    for _ in range(90):
        page.wait_for_timeout(500)
        kin = int(page.evaluate(_KIN_JS))
        if kin:
            break
    page.wait_for_timeout(800)
    return kin


def _search_sweep(ctx: Ctx, page: Any, width: int) -> list[tuple[str, bool]]:
    """Обе строки выдачи поиска и ряд серии карточки: они той же породы, что полки."""
    found = _open_search(ctx, page, _FULL_SEARCH)
    if found <= 0:
        return [(f"поиск {width}: выдача не доехала или не успокоилась за 60 с", False)]
    swept = [_bars_sweep(page, f"поиск {width}x1 ({found} находок)", 4)]
    kin = _open_card(page)
    if not kin:
        return [*swept, (f"карточка {width}: ряда серии не дождались", False)]
    return [*swept, _bars_sweep(page, f"карточка {width}x1 (ряд серии, {kin} плиток)", 4)]


def check_26_bars(ctx: Ctx) -> Result:
    """Своей прокрутки у строки плиток нет: ``scrollHeight == clientHeight``, полос нет нигде.

    Каждая строка (полки главной, обе строки выдачи поиска, ряд серии карточки) в покое и
    под наведением на каждую из первых плиток: ни вертикальной полосы, ни видимой
    горизонтальной, у подписи горящей плитки тоже, плитка с обводкой рамки и подписью
    вмещается в строку целиком. Полки - в окнах 1280, 1440 и 1920 по ширине при масштабе
    1 и 1.5, поиск и карточка - в 1280 и 1920. 🔴 Полосы видны только потому, что ``main``
    снимает с Chromium флаг ``--hide-scrollbars``: с ним ширина полосы всегда 0.
    """
    browser = ctx.page.context.browser
    notes: list[str] = []
    ok = True
    for width in (1280, 1440, 1920):
        for scale in (1.0, 1.5):
            page = browser.new_page(
                viewport={"width": width, "height": 900}, device_scale_factor=scale
            )
            try:
                if _open_shelves(page, ctx.base) < 2:
                    note, good = f"{width}x{scale:g}: полки не доехали", False
                else:
                    note, good = _bars_sweep(page, f"{width}x{scale:g}", 6)
            finally:
                page.close()
            notes.append(note)
            ok = ok and good
    for width in (1280, 1920):
        page = browser.new_page(viewport={"width": width, "height": 900})
        try:
            swept = _search_sweep(ctx, page, width)
        finally:
            page.close()
        notes += [note for note, _ in swept]
        ok = ok and all(good for _, good in swept)
    return Result(26, "Полосы", ok, None, "; ".join(notes))


def check_27_under_pointer(ctx: Ctx) -> Result:
    """После прокрутки под неподвижной мышью горит плитка, которая теперь под указателем.

    Прокрутка событий мыши не рождает: полка, уехавшая вбок (боковое колесо, кнопка над
    полкой), или страница, пролистанная колесом, оставляли гореть плитку, которой под
    указателем уже нет, пока человек не шевельнёт мышью.
    """
    page = ctx.page
    if _open_shelves(page, ctx.base) < 1:
        return Result(27, "Под мышью", False, "полки не доехали", "на главной нет полки с плитками")
    row = int(page.evaluate("() => __tcShelf.overflow()"))
    if row < 0:
        detail = "ни одна полка не шире окна - уехать из-под указателя плитке некуда"
        return Result(27, "Под мышью", False, "нет переполненной полки", detail)
    page.evaluate("(r) => __tcShelf.lift(r, 150)", row)
    _hover(page, row, 1)
    spot = page.evaluate("([r, i]) => __tcShelf.point(r, i)", [row, 1])
    moves: list[tuple[str, Callable[[], object]]] = [
        ("боковое колесо", lambda: page.mouse.wheel(470, 0)),
        (
            "scrollBy полки",
            lambda: page.evaluate(
                "(r) => __tcShelf.rows()[r].scrollBy({ left: 470, behavior: 'instant' })", row
            ),
        ),
        ("колесо страницы", lambda: page.mouse.wheel(0, 200)),
    ]
    notes: list[str] = []
    ok = True
    for label, move in moves:
        pose = page.evaluate("() => __tcShelf.pose()")
        move()
        _settle(page)
        moved = page.evaluate("() => __tcShelf.pose()") != pose
        under = page.evaluate("([x, y]) => __tcShelf.under(x, y)", [spot["x"], spot["y"]])
        lit = page.evaluate("() => __tcShelf.now()")["lit"]
        ok = ok and moved and lit == under
        notes.append(
            f"{label}: {'поехало' if moved else 'НЕ поехало'}, под указателем {under}, горит {lit}"
        )
    return Result(
        27, "Под мышью", ok, None, f"полка {row}, указатель на плитке 1: " + "; ".join(notes)
    )


def check_18_caption_scroll(ctx: Ctx) -> Result:
    """Автопрокрутка подписи: настоящая переполненная подпись едет вниз и обратно при наведении.

    Пункт сперва ищет на живой полке плитку, чья НАСТОЯЩАЯ подпись после разворота
    (`is-lit`) не влезает в отведённые две строки. Синтетическую подпись он себе не
    рисует: если такой плитки не нашлось ни одной, это отдельная находка о самой полке,
    а не повод подменить пробу и объявить пункт зелёным.
    """
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    # На груженом стенде полки приезжают секундами ПОСЛЕ load: скан по ещё пустой
    # странице молча объявляет «длинных подписей нет», хотя они есть. Ждём первой
    # плитки; не дождались ни одной - это и есть ответ скану (упадёт ниже честно).
    for _ in range(60):
        if ctx.page.evaluate("document.querySelectorAll('.tc-tile[data-tc-focusable]').length"):
            break
        ctx.page.wait_for_timeout(500)
    ctx.page.wait_for_timeout(300)
    # Переполнение меряется при том же раскладе, что создаёт само наведение: `is-lit`
    # разворачивает подпись в несколько строк внутри короба той же высоты.
    candidate = ctx.page.evaluate(
        """
        () => {
            const tiles = Array.from(document.querySelectorAll('.tc-tile[data-tc-focusable]'));
            for (let i = 0; i < tiles.length; i++) {
                const tile = tiles[i];
                const box = tile.querySelector('.tc-tile-cap');
                if (!box) continue;
                tile.classList.add('is-lit');
                const overflow = box.scrollHeight - box.clientHeight;
                tile.classList.remove('is-lit');
                box.scrollTop = 0;
                if (overflow > 4) {
                    const title = tile.querySelector('.tc-caption');
                    return { index: i, overflow, title: title ? title.textContent : '' };
                }
            }
            return null;
        }
        """
    )
    if candidate is None:
        detail = (
            "настоящих длинных подписей на полке нет - ни одна не переполняет отведённые две строки"
        )
        return Result(18, "Подпись", False, "нет переполненной подписи на живой полке", detail)

    ctx.page.evaluate(
        """
        (i) => document.querySelectorAll('.tc-tile[data-tc-focusable]')[i]
            .scrollIntoView({ block: 'center', inline: 'center' })
        """,
        candidate["index"],
    )
    # 🔴 Точку наведения нельзя снимать сразу после `scrollIntoView`: у полки
    # `scroll-behavior: smooth`, и плитка, ушедшая за край, едет вбок ещё сотни
    # миллисекунд. Свежеснятый rect при этом протухший - указатель ложится туда,
    # где плитки уже нет (или ещё нет), pointermove бьёт в пустоту и больше не
    # срабатывает: прокрутка под НЕПОДВИЖНЫМ указателем события не даёт. Пункт
    # тогда меряет нулевой scrollTop у здоровой подписи. Ждём, пока рамка встанет.
    rect = None
    for _ in range(40):
        ctx.page.wait_for_timeout(50)
        fresh = ctx.page.evaluate(
            """
            (i) => {
                const r = document.querySelectorAll('.tc-tile[data-tc-focusable]')[i]
                    .getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }
            """,
            candidate["index"],
        )
        if (
            rect is not None
            and abs(fresh["x"] - rect["x"]) < 0.5
            and abs(fresh["y"] - rect["y"]) < 0.5
        ):
            break
        rect = fresh
    # Увод в инертный угол перед самим наведением: гасит выделение, оставшееся от
    # прошлых пунктов (ряд при этом сдувается и раскладка едет - поэтому точку
    # снимаем заново, ПОСЛЕ увода), и гарантирует, что следующий `mouse.move`
    # сменит позицию указателя и pointermove правда случится. Само наведение -
    # РОВНО одно движение: второе пришлось бы уже по раздутой рядом раскладке,
    # где под указателем оказывается соседняя плитка и выделение уходит на неё.
    ctx.page.mouse.move(5, 5)
    ctx.page.wait_for_timeout(150)
    rect = ctx.page.evaluate(
        """
        (i) => {
            const r = document.querySelectorAll('.tc-tile[data-tc-focusable]')[i]
                .getBoundingClientRect();
            return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
        """,
        candidate["index"],
    )
    ctx.page.mouse.move(rect["x"], rect["y"])
    ctx.page.wait_for_timeout(60)
    samples: list[int] = []
    for _ in range(6):
        value = ctx.page.evaluate(
            """
            (i) => document.querySelectorAll('.tc-tile[data-tc-focusable]')[i]
                .querySelector('.tc-tile-cap').scrollTop
            """,
            candidate["index"],
        )
        samples.append(int(value))
        ctx.page.wait_for_timeout(220)

    run = 1
    best_run = 1
    for prev, cur in itertools.pairwise(samples):
        run = run + 1 if cur > prev else 1
        best_run = max(best_run, run)
    rising = best_run >= 3

    ctx.page.mouse.move(5, 5)
    ctx.page.wait_for_timeout(150)
    after_leave = int(
        ctx.page.evaluate(
            """
        (i) => document.querySelectorAll('.tc-tile[data-tc-focusable]')[i]
            .querySelector('.tc-tile-cap').scrollTop
        """,
            candidate["index"],
        )
    )

    ok = rising and after_leave == 0
    detail = (
        f"настоящая переполненная подпись найдена ({candidate['title']!r}, "
        f"переполнение {candidate['overflow']} px); scrollTop во времени {samples} "
        f"(подряд растущих отсчётов: {best_run}); после увода указателя scrollTop={after_leave}"
    )
    return Result(18, "Подпись", ok, None, detail)


def _cyrillic_split(names: list[str]) -> tuple[int, list[str]]:
    """Сколько имён из списка несут кириллицу и какие именно - для печати, не для суда."""
    hits = [name for name in names if _CYRILLIC_RE.search(name)]
    return len(hits), hits


def check_19_latin_titles(ctx: Ctx) -> Result:
    """При языке `en` латинское имя картины идёт на экран, если оно записано.

    🔴 Решение по объёму судимого (карточка TC-1140): пункт судит РОВНО одну пробу, а
    не число оставшейся кириллицы на полках/поиске/родне - и это не недосмотр, а выбор.
    Автоматического порога «сколько кириллицы много» не бывает: у части картин
    латинского имени нет вовсе (`torrcast/domain/spoken_title.py`), и экран законно
    показывает записанное имя как есть. Судить по числу значило бы либо красить пункт
    на легальных непереведённых именах (ложный красный), либо занижать порог до
    бесполезности (ложный зелёный на настоящей порче). Три диагностических числа
    остаются в печати для человека, но получают пометку «не судится», чтобы название
    пункта не обещало больше, чем он проверяет: единственное судимое - отрицательная
    проба, у картины с известным латинским именем («Матрица» → «The Matrix») экран
    обязан показать именно его.
    """
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_timeout(300)

    shelves = ctx.page.evaluate(
        """
        () => Array.from(document.querySelectorAll('.tc-shelf')).map((shelf) => {
            const head = shelf.querySelector('.tc-section');
            const caps = Array.from(shelf.querySelectorAll('.tc-tile-cap .tc-caption'));
            return {
                label: head ? head.textContent : '(без заголовка)',
                names: caps.map((c) => c.textContent || ''),
            };
        })
        """
    )
    shelf_parts = []
    for shelf in shelves:
        cyr_n, cyr_names = _cyrillic_split(shelf["names"])
        shelf_parts.append(f"{shelf['label']}: {cyr_n} из {len(shelf['names'])} {cyr_names}")

    placeholder = ctx.english.get("web.search.placeholder", "")
    field = ctx.page.get_by_placeholder(placeholder, exact=True) if placeholder else None
    search_part = "поле поиска не найдено"
    if field is not None and field.count() > 0:
        field.first.fill(_LATIN_KNOWN_TITLE)
        field.first.press("Enter")
        began = time.monotonic()
        tiles = ctx.page.locator(_LIVE_TILE)
        while time.monotonic() - began < 15.0 and tiles.count() == 0:
            ctx.page.wait_for_timeout(300)
        names = ctx.page.eval_on_selector_all(
            "[data-tc-tile] .tc-tile-cap .tc-caption", "els => els.map((e) => e.textContent || '')"
        )
        cyr_n, cyr_names = _cyrillic_split(names)
        search_part = f"{cyr_n} из {len(names)} {cyr_names}"

    # Родня едет фоном (см. `_card_of`): не согреть кэш здесь значит всегда печатать
    # ноль по холодному экземпляру, каким бы стоящим ни было судимое рядом. Согреваем
    # тем же путём, каким карточку спрашивает продукт, - сырым HTTP до X-Torrcast-Partial.
    _card_of(ctx.base, _LATIN_KNOWN_TITLE)

    card_part = "карточка не открылась - пробу не с чем сверять"
    card_title = ""
    related_part = ""
    live_tiles = ctx.page.locator(_LIVE_TILE)
    if live_tiles.count() > 0:
        live_tiles.first.click()
        card = ctx.page.locator("[data-tc-card]")
        try:
            card.first.wait_for(state="visible", timeout=15000)
        except Exception:  # у playwright свой класс исключения; ловим отсутствие узла
            card = None
        if card is not None:
            deadline = time.monotonic() + _PARTIAL_WAIT
            title_node = card.locator(".tc-title-detail")
            while time.monotonic() < deadline:
                card_title = title_node.inner_text() if title_node.count() else ""
                if card_title.strip():
                    break
                ctx.page.wait_for_timeout(1000)
            card_part = f"заголовок {card_title!r}"
            related_names = ctx.page.eval_on_selector_all(
                ".tc-detail-series-block .tc-tile-cap .tc-caption",
                "els => els.map((e) => e.textContent || '')",
            )
            if related_names:
                cyr_n, cyr_names = _cyrillic_split(related_names)
                related_part = (
                    f"; похожее (не судится): {cyr_n} из {len(related_names)} {cyr_names}"
                )
            else:
                related_part = "; похожее (не судится): полки родни на этой карточке нет"

    negative_ok = bool(card_title.strip()) and not _CYRILLIC_RE.search(card_title)
    ok = negative_ok
    detail = (
        f"полки главной (не судится): {'; '.join(shelf_parts) or 'полок нет'}; "
        f"поиск «{_LATIN_KNOWN_TITLE}» (не судится): {search_part}; "
        f"карточка «{_LATIN_KNOWN_TITLE}»: {card_part}{related_part}; "
        f"проба «латинское имя есть → на экране латиница» (судимое): {negative_ok}"
    )
    # Возвращаем страницу в состояние «главная»: следующие пункты (поиск, карточка)
    # ждут этого стартового условия так же, как после пункта 1.
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_timeout(300)
    return Result(19, "Латиница", ok, None, detail)


def _call_page_fn(ctx: Ctx, holder: str, name: str, args: list[Any]) -> dict[str, Any]:
    """Вызвать функцию страницы, сверив число её параметров с числом аргументов.

    🔴 Пункт 21 звал `TCHome._mergeHits` двумя аргументами, а тот принимает три и
    начинается с `if (!partial) return fresh` - утверждение мерило `return fresh`,
    то есть НИЧЕГО, и оставалось зелёным на любом сломанном слиянии. Позиционный
    вызов пустеет молча всякий раз, как у функции страницы появляется параметр, и
    поймать это можно только ЧИСЛОМ: `fn.length` против длины списка аргументов.

    Цена приёма названа прямо: параметр, добавленный продуктом, красит пункт, пока
    прибор не научат новому вызову. Красный пункт - это и есть сигнал; молчаливая
    зелень на невызванной логике дороже.
    """
    answer: dict[str, Any] = ctx.page.evaluate(
        "([holder, name, args]) => {"
        " const host = window[holder]; const fn = host && host[name];"
        " if (typeof fn !== 'function') return {missing: true};"
        " if (fn.length !== args.length) return {arity: fn.length};"
        " return {value: fn.apply(host, args)}; }",
        [holder, name, args],
    )
    if answer.get("missing"):
        return {"error": f"window.{holder}.{name} не найден"}
    if "arity" in answer:
        return {
            "error": (
                f"window.{holder}.{name}: параметров {answer['arity']}, "
                f"а прибор передаёт {len(args)} - утверждение мерит не ту функцию"
            )
        }
    return {"value": answer.get("value")}


#: Что обязано выдержать слияние плиток: имя, показанное, свежее, `partial`, заголовки.
_MERGE_CASES: tuple[
    tuple[str, list[dict[str, str]], list[dict[str, str]], bool, list[str]], ...
] = (
    (
        "два плана одной картины под одним key",
        [],
        [{"key": "k", "title": "A"}, {"key": "k", "title": "B"}],
        True,
        ["A", "B"],
    ),
    (
        "частичный ответ не отнимает показанную плитку",
        [{"key": "a", "title": "A"}],
        [{"key": "b", "title": "B"}],
        True,
        ["A", "B"],
    ),
    (
        "частичный ответ обновляет одноключевую пару порознь",
        [{"key": "k", "title": "A"}, {"key": "k", "title": "B"}],
        [{"key": "k", "title": "A2"}, {"key": "k", "title": "B2"}],
        True,
        ["A2", "B2"],
    ),
    (
        "законченный круг заменяет выдачу целиком",
        [{"key": "a", "title": "A"}],
        [{"key": "b", "title": "B"}],
        False,
        ["B"],
    ),
)


def check_21_merge_hits(ctx: Ctx) -> Result:
    """Слияние плиток поиска: оба режима `TCHome._mergeHits`, а не первая его строка.

    Один `key` носят два РАЗНЫХ плана одной картины (сервер отдаёт их честно), и мерж
    по голому `key` хоронил второй молча, без единой ошибки: личность плитки - `key`
    плюс номер её повторения по счёту. Это первое утверждение пункта.

    Остальные три держат то, что слияние делает сверх этого. Пока круг не закончен
    (`partial`), показанная плитка остаётся на своём месте, даже если её нет в свежем
    ответе: превью круга между шагами пустеет, и отнимать по нему нельзя. Законченный
    круг, наоборот, заменяет выдачу ЦЕЛИКОМ - порядок находок продуктовый и берётся у
    круга, а не у того, кто ответил первым.

    Проверяется код напрямую, а не живым поиском: `TCHome` - обычный глобальный объект
    (`const TCHome = {...}` в `home.js`, простой `<script>` без `type="module"`), и
    `window.TCHome._mergeHits` доступен сразу после `page.goto` на главную. Замер не
    зависит ни от состояния пула, ни от конкретных картин - только от кода функции.
    """
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    parts: list[str] = []
    ok = True
    for name, known, fresh, partial, want in _MERGE_CASES:
        answer = _call_page_fn(ctx, "TCHome", "_mergeHits", [known, fresh, partial])
        if "error" in answer:
            return Result(21, "Слияние", False, None, str(answer["error"]))
        merged = answer.get("value") or []
        titles = [one.get("title") if isinstance(one, dict) else one for one in merged]
        ok = ok and titles == want
        parts.append(f"{name}: {titles}, ждали {want}")
    return Result(21, "Слияние", ok, None, "; ".join(parts))


def _shelf_tiles(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Сами плитки по полкам из `/api/shelves`, в тех же двух формах ответа.

    🔴 Пустая полка остаётся в выдаче ПУСТОЙ, а не выбрасывается: фильтр `if tiles`
    прятал опустевшую полку от всех троих судей (15, 16, 22) разом - они судили
    выжившую, и главная с одной пустой полкой зеленела.
    """
    shelves: dict[str, list[dict[str, Any]]] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            # Не всякое поле ответа - полка: рядом с ними лежит время сборки строкой
            # (`built_at`), и вопрос «а нет ли внутри плиток» валил скрипт целиком.
            tiles = value if isinstance(value, list) else _inner(value)
            if isinstance(tiles, list):
                shelves[str(key)] = [one for one in tiles if isinstance(one, dict)]
    return shelves


def _inner(value: Any) -> Any:
    """Плитки полки, названной объектом; поле не полка вовсе - ``None``."""
    return value.get("tiles") if isinstance(value, dict) else None


def check_15_posters(base: str) -> Result:
    """Обложки: доля плиток с картинкой не ниже 60% в каждой непустой полке.

    Эта планка своего номера среди прочих пунктов не получила, и мерить её было нечем:
    пункт 1 считает ПЛИТКИ, а не картинки на них. Полка из одних букв - законный вид
    главной по остальным пунктам, и первым это увидел бы человек, а не скрипт.

    Доля считается по ПЕРВЫМ 30 плиткам, тем же окном, каким соседний пункт меряет
    мусор: столько видно на экране, а хвост полки человек листает уже зная, что
    показывают.
    """
    code, body = _get(base + "/api/shelves")
    if code != 200:
        return Result(15, "Обложки", False, None, f"GET /api/shelves -> {code}")
    try:
        shelves = _shelf_tiles(json.loads(body))
    except json.JSONDecodeError as exc:
        return Result(15, "Обложки", False, None, f"тело не JSON: {exc}")
    shares: dict[str, str] = {}
    empty: list[str] = []
    ok = bool(shelves)
    for key, tiles in shelves.items():
        if not tiles:
            # Полка без единой плитки - отказ, а не «обложки в порядке»: доля на
            # пустом окне верна сама по себе, и пункт зеленел бы ровно тогда, когда
            # смотреть не на что.
            empty.append(key)
            ok = False
            continue
        head = tiles[:_SHELF_WINDOW]
        with_poster = sum(1 for one in head if str(one.get("poster") or ""))
        shares[key] = f"{with_poster}/{len(head)}"
        if with_poster < _POSTER_BAR * len(head):
            ok = False
    detail = f"планка {_POSTER_BAR:.0%}, по полкам {shares}"
    if empty:
        detail += f"; ПУСТЫЕ полки: {', '.join(empty)}"
    return Result(15, "Обложки", ok, None, detail)


def check_16_junk(base: str) -> Result:
    """Мусор: ни одной не-киношной плитки в первых 30 каждой полки.

    Приметы тут СВОИ, а не продуктовые: скрипт, спрашивающий продукт его же правилом,
    подтверждал бы, что правило применилось, а не что мусора нет. Продукт отсеивает по
    имени РАЗДАЧИ, скрипт смотрит на титул готовой ПЛИТКИ - разные концы тракта, и
    «Mortal Kombat ... PC | RePack» проехал бы первый и остался виден второму.

    Ноль плиток - это отказ, а не «мусора нет»: на пустой выдаче условие «ни одной
    не-киношной» верно само по себе, и пункт зеленел бы ровно тогда, когда смотреть
    было не на что. Сколько плиток осмотрено, пункт называет числом (так же, как
    соседний пункт 15 объявляет отсутствие полок красным, а не тихим OK).
    """
    code, body = _get(base + "/api/shelves")
    if code != 200:
        return Result(16, "Мусор", False, None, f"GET /api/shelves -> {code}")
    try:
        shelves = _shelf_tiles(json.loads(body))
    except json.JSONDecodeError as exc:
        return Result(16, "Мусор", False, None, f"тело не JSON: {exc}")
    caught: list[str] = []
    looked = 0
    empty = [key for key, tiles in shelves.items() if not tiles]
    for key, tiles in shelves.items():
        for one in tiles[:_SHELF_WINDOW]:
            looked += 1
            title = f"{one.get('title') or ''} {one.get('original') or ''}"
            found = _JUNK_RE.search(title)
            if found:
                caught.append(f"{key}: {title.strip()!r} по слову {found.group()!r}")
    if not looked:
        empty_detail = f"полок {len(shelves)}, плиток 0 - мусор искать не в чем"
        return Result(16, "Мусор", False, None, empty_detail)
    seen = f"осмотрено плиток {looked} в {len(shelves)} полках"
    detail = f"{seen}; " + ("; ".join(caught) if caught else "мусора нет")
    if empty:
        # Опустевшая полка - отказ того же рода, что и пустая выдача целиком: судить
        # мусор по выжившим полкам значит зеленеть на главной, где смотреть нечего.
        detail += f"; ПУСТЫЕ полки: {', '.join(empty)}"
    return Result(16, "Мусор", not caught and not empty, None, detail)


#: Ведущие плитки полки, которые проверяет пункт 22 - тем же окном, каким человек их
#: видит на экране без прокрутки, не всей полкой разом.
_CARD_OPEN_WINDOW: Final = 12
#: Отпущенное время одного открытия карточки в пункте 22. По живому замеру на том же
#: стенде (10-09-2026) холодный отклик `/api/card` - опрос пула индексеров - доходит
#: до 11.7 с, и умолчание `_get` в 10 с резало штатный, пусть и медленный, ответ.
#: Потолок 20 с даёт запас ~1.7x над худшим замеренным, как `_POSITION_GROWTH_WAIT`
#: над худшим промежутком позиции. Молчание дольше этого - уже дефект продукта, и
#: пункт обязан показать его красным, а не переждать.
_CARD_GET_WAIT: Final = 20.0


def check_22_shelf_cards_open(base: str) -> Result:
    """С плитки полки «Новинки» карточка обязана открываться, а не 404.

    Найдено соседней полосой (TC-1139) и снято на стенде 07-09-2026, не мной: все
    двенадцать проверенных ведущих плиток полки «Новинки» отвечали `404 not_found`
    на `/api/card`. Чужая правка `web/card.py`/`search_circle`/`card_lookup` это
    починила (10-09-2026 на сведённом `dev`: 12 из 12 отвечают 200), и пункт стоит
    сторожем регресса. Отдельный приговор - молчание: отклик дольше
    `_CARD_GET_WAIT` считается по своей строке и называется таймаутом с числом, а
    не сливается с отказами по коду и не роняет пункт в «скрипт упал».
    """
    code, body = _get(base + "/api/shelves")
    if code != 200:
        return Result(22, "Полка → карточка", False, None, f"GET /api/shelves -> {code}")
    try:
        shelves = _shelf_tiles(json.loads(body))
    except json.JSONDecodeError as exc:
        return Result(22, "Полка → карточка", False, None, f"тело не JSON: {exc}")
    if "fresh" not in shelves:
        detail = f"полки «Новинки» (fresh) в выдаче нет; приехали: {sorted(shelves)}"
        return Result(22, "Полка → карточка", False, None, detail)
    tiles = shelves["fresh"]
    if not tiles:
        # 🔴 Пустая «Новинки» - отказ, а не повод молча судить ДРУГУЮ полку: откат
        # `or next(iter(...))` подставлял соседнюю, и пункт зеленел по плиткам, о
        # которых его имя ничего не обещало.
        empty_detail = "полка «Новинки» пуста - нечего открывать"
        return Result(22, "Полка → карточка", False, None, empty_detail)
    window = tiles[:_CARD_OPEN_WINDOW]
    opened = 0
    stalled = 0
    failures: list[str] = []
    for one in window:
        key = str(one.get("key") or "")
        query = str(one.get("query") or one.get("title") or "")
        if not key or not query:
            failures.append(f"{key!r}: нет query/title, спрашивать нечем")
            continue
        url = f"{base}/api/card/{urllib.parse.quote(key)}?query={urllib.parse.quote(query)}"
        card_code, card_body = _get(url, timeout=_CARD_GET_WAIT)
        if card_code == 200:
            opened += 1
            continue
        if card_code == 0:
            stalled += 1
            why = card_body.decode("utf-8", "replace")[:160]
        else:
            why = ""
            with contextlib.suppress(json.JSONDecodeError):
                why = str(json.loads(card_body).get("error", ""))
        failures.append(f"{key!r} ({query!r}): код {card_code} {why}".rstrip())
    ok = opened == len(window)
    detail = (
        f"открылось {opened}/{len(window)} с полки «Новинки», "
        f"встало по времени/сети {stalled}; отказы: " + ("; ".join(failures) if failures else "нет")
    )
    return Result(22, "Полка → карточка", ok, None, detail)


def check_2_search(ctx: Ctx) -> Result:
    """Поиск: «Интерстеллар» → плитка с 2014 в первых трёх за ≤15 с."""
    # Главную пункт открывает сам: под `--only 2` страница - `about:blank`, поля нет.
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    placeholder = ctx.english.get("web.search.placeholder", "")
    field = ctx.page.get_by_placeholder(placeholder, exact=True) if placeholder else None
    if field is None or field.count() == 0:
        detail = f"поле поиска не найдено: input[placeholder={placeholder!r}] нет в DOM"
        return Result(2, "Поиск", False, None, detail)
    field.first.fill(_MOVIE_TITLE)
    field.first.press("Enter")
    began = time.monotonic()
    tiles = ctx.page.locator("[data-tc-tile]")
    seen_count = 0
    found_2014 = False
    while time.monotonic() - began < 15.0:
        seen_count = tiles.count()
        if seen_count:
            texts = [tiles.nth(i).inner_text() for i in range(min(3, seen_count))]
            if any("2014" in text for text in texts):
                found_2014 = True
                break
        ctx.page.wait_for_timeout(300)
    spent = time.monotonic() - began
    detail = (
        f"поле найдено, ввод отправлен; за {spent:.1f} с плиток [data-tc-tile]: {seen_count}; "
        f"2014 среди первых трёх: {found_2014}"
    )
    return Result(2, "Поиск", found_2014, None, detail)


def check_3_card(ctx: Ctx, search_ok: bool) -> Result:
    """Карточка: описание непусто, рейтинг - число, озвучек ≥1, «Играть» активна."""
    tiles = ctx.page.locator(_LIVE_TILE)
    if tiles.count() == 0:
        reason = "пункт 2" if not search_ok else None
        return Result(3, "Карточка", False, reason, "нет живых плиток - открывать нечем")
    tiles.first.click()
    card = ctx.page.locator("[data-tc-card]")
    try:
        card.first.wait_for(state="visible", timeout=15000)
    except Exception:  # у playwright свой класс исключения; ловим отсутствие узла
        return Result(3, "Карточка", False, None, "клик по плитке не открыл [data-tc-card]")
    # Карточка приезжает пустой каркасом и наполняется фоном (справка, озвучки): судить
    # её через 500 мс значит мерить скорость сети. Ждём появления описания, а не времени.
    deadline = time.monotonic() + _PARTIAL_WAIT
    desc_node = card.locator("[data-tc-card-description]")
    description = ""
    while time.monotonic() < deadline:
        description = desc_node.inner_text() if desc_node.count() else ""
        if description.strip():
            break
        ctx.page.wait_for_timeout(1000)
    rating_node = card.locator("[data-tc-card-rating]")
    rating_text = rating_node.inner_text() if rating_node.count() else ""
    # Рейтинг человеку показывается с источником («IMDb 8.7») - так велит каталог, и
    # голая цифра на экране не значила бы ничего. Скрипт ищет ЧИСЛО внутри строки.
    rating_ok = bool(_NUMBER_RE.search(rating_text))
    audio_count = card.locator("[data-tc-audio-option]").count()
    play_button = card.locator("[data-tc-play]")
    play_ok = play_button.count() > 0 and bool(play_button.first.is_enabled())
    ok = bool(description.strip()) and rating_ok and audio_count >= 1 and play_ok
    detail = (
        f"описание {'непусто' if description.strip() else 'ПУСТО'} ({len(description)} симв.); "
        f"рейтинг {rating_text!r} ({'число' if rating_ok else 'не число'}); "
        f"озвучек {audio_count}; «Играть» {'активна' if play_ok else 'недоступна/отсутствует'}"
    )
    return Result(3, "Карточка", ok, None, detail)


def _wake_panel(ctx: Ctx) -> None:
    """Разбудить панель плеера движением мыши - ровно так, как это делает зритель.

    🔴 Через 3 с простоя (``TCPlayer.IDLE_MS``) панель уходит в ``.is-idle`` и получает
    ``pointer-events: none``: клик по её кнопке перехватывает `<video>`, и скрипт без
    движения мышью получал таймаут вместо ответа продукта.
    """
    box = ctx.page.viewport_size or {"width": 1280, "height": 720}
    ctx.page.mouse.move(box["width"] / 2, box["height"] / 2)
    ctx.page.mouse.move(box["width"] / 2 + 8, box["height"] / 2 + 8)
    ctx.page.wait_for_timeout(100)


def _playback_guard(
    number: int, name: str, ctx: Ctx, prev_ok: bool, prev_reason: str
) -> Result | None:
    """Общий тормоз показа (пункты 4, 6, 7-9): чинить нечего - идти некуда без прошлого шага."""
    if not prev_ok:
        return Result(number, name, False, prev_reason, "предыдущий шаг показа не пройден")
    if not ctx.allow_play:
        state_code, state_body = _get(ctx.base + "/api/state")
        state_text = (
            state_body.decode("utf-8", "replace")[:200]
            if state_code == 200
            else f"код {state_code}"
        )
        blocked = "показ выключен этим прогоном (--play не задан): полоса упаковки занята соседом"
        return Result(number, name, False, blocked, f"/api/state сейчас: {state_text}")
    return None


def _await_playback(ctx: Ctx) -> bool:
    """Дождаться первого кадра: `<video>` в DOM и `readyState >= 3` (есть что показывать)."""
    with contextlib.suppress(Exception):
        ctx.page.wait_for_selector("video", timeout=_PLAY_START_WAIT)
        ctx.page.wait_for_function(
            "() => { const v = document.querySelector('video'); return !!v && v.readyState >= 3; }",
            timeout=_PLAY_START_WAIT,
        )
        return True
    return False


def check_4_playback(ctx: Ctx, card_ok: bool) -> Result:
    """Показ: `video.currentTime` растёт монотонно 60 с, без stall дольше 3 с."""
    guard = _playback_guard(4, "Показ", ctx, card_ok, "пункт 3 («Играть» недоступна)")
    if guard:
        return guard
    ctx.page.locator("[data-tc-play]").first.click()
    # Кнопка только КЛАДЁТ заказ: продукт ещё ищет раздачу, качает метаданные и пакует
    # первые куски. Судить ровность хода до первого кадра значило бы мерить прогрев, а
    # не показ, поэтому 60 с ровности отсчитываются от `readyState >= 3`, а не от клика.
    if not _await_playback(ctx):
        waited = _PLAY_START_WAIT / 1000.0
        why = f"картинка не пошла за {waited:.0f} с после «Играть»"
        return Result(4, "Показ", False, None, why)
    began = time.monotonic()
    last = -1.0
    first = 0.0
    grew, total, dropped = 0, 0, 0
    stalled_since: float | None = None
    worst_stall = 0.0
    samples = 0
    while time.monotonic() - began < 60.0:
        now = time.monotonic()
        current = float(ctx.page.eval_on_selector("video", "v => v.currentTime"))
        stalled = bool(ctx.page.eval_on_selector("video", "v => v.readyState < 3"))
        if not stalled:
            stalled_since = None
        elif stalled_since is None:
            stalled_since = now
        else:
            worst_stall = max(worst_stall, now - stalled_since)
        if last >= 0:
            total += 1
            grew += current > last
            dropped += current < last
        else:
            first = current
        last, samples = current, samples + 1
        time.sleep(1.0)
    # ТЗ просит ход монотонный и без провала длиннее 3 с. Провал в 3 с - это и есть
    # весь допуск на нерастущие пары, и `grew` СУДИТСЯ этим допуском: замерший, но
    # набитый буфером кадр (`currentTime` стоит, `readyState >= 3`, провала по
    # readyState нет) обязан краснеть, а не зеленеть числом, которое считалось только
    # для печати. Откат назад (пара с убылью) допуском не покрыт ничем.
    ok = total > 0 and dropped == 0 and worst_stall <= 3.0 and grew >= total - 3
    detail = (
        f"{samples} замеров за 60 с, ход {last - first:.1f} с, растущих пар {grew}/{total}, "
        f"пар с откатом {dropped}, худший провал {worst_stall:.1f} с"
    )
    return Result(4, "Показ", ok, None, detail)


#: Куда скрипт ставит показ перед остановкой, секунды от начала КАРТИНЫ.
_BOOKMARK_AT: Final = 90.0
#: Сколько ждать, пока закладка догонит остановленную вкладку, секунды. Вкладка шлёт
#: место раз в ``TCPlayer.POSITION_MS`` (2 с), а сторож кладёт его в запись раз в
#: :data:`torrcast.usecases.watch.WATCH_SECONDS` (10 с) - полсекунды тут мерили такт.
_BOOKMARK_WAIT: Final = 30.0


def check_5_bookmark(ctx: Ctx, play_ok: bool) -> Result:
    """Закладка: стоп на 90-й секунде → `WatchState`/`/api/state` даёт `pos` в 90±3.

    🔴 До 90-й секунды показ ПЕРЕМАТЫВАЕТСЯ, а не досиживается. Поток - полносеточный
    VOD всей картины, и `currentTime` у него считает от начала КАРТИНЫ, а не от начала
    показа: поднявшись с прежней закладки (по живому замеру «Интерстеллар» поехал с
    410,9 с), вкладка уже на первом же круге больше девяноста - скрипт мерил место
    старой закладки и звал это провалом продукта.
    """
    if not play_ok:
        return Result(5, "Закладка", False, "пункт 4 (показ не идёт)", "остановить нечего")
    ctx.page.eval_on_selector("video", f"v => {{ v.currentTime = {_BOOKMARK_AT}; }}")
    began = time.monotonic()
    current = 0.0
    while time.monotonic() - began < 30.0:
        current = float(ctx.page.eval_on_selector("video", "v => v.currentTime"))
        if abs(current - _BOOKMARK_AT) <= 2.0:
            break
        time.sleep(0.5)
    ctx.page.eval_on_selector("video", "v => v.pause()")
    position = None
    began = time.monotonic()
    while time.monotonic() - began < _BOOKMARK_WAIT:
        code, body = _get(ctx.base + "/api/state")
        if code == 200:
            with contextlib.suppress(json.JSONDecodeError):
                position = json.loads(body).get("position")
        if isinstance(position, int | float) and abs(position - _BOOKMARK_AT) <= 3.0:
            break
        time.sleep(1.0)
    ok = isinstance(position, int | float) and abs(position - _BOOKMARK_AT) <= 3.0
    where = f"{_BOOKMARK_AT:.0f}"
    detail = f"перемотка на {where} с, стоп у {current:.1f}; /api/state position={position!r}"
    return Result(5, "Закладка", ok, None, detail)


def check_6_restart(ctx: Ctx, bookmark_ok: bool) -> Result:
    """Сначала: повторный заход → кнопка есть, после клика `currentTime` < 5."""
    guard = _playback_guard(6, "Сначала", ctx, bookmark_ok, "пункт 5 (закладки нет)")
    if guard:
        return guard
    # 🔴 «Сначала» живёт на КАРТОЧКЕ картины (`web.detail.start_over`), а не на главной:
    # главная предлагает продолжить полкой «Продолжить», и искать кнопку там - значит
    # звать дефектом раскладку, которую продукт задаёт нарочно.
    refusal = _open_card_by_page(ctx, _MOVIE_TITLE)
    if refusal is not None:
        return Result(6, "Сначала", False, None, refusal)
    label = ctx.english.get("web.detail.start_over", "")
    button = ctx.page.get_by_text(label, exact=True) if label else None
    if button is None or button.count() == 0:
        return Result(6, "Сначала", False, None, f"кнопка {label!r} не найдена на карточке")
    button.first.click()
    # Клик лишь КЛАДЁТ заказ: продукту ещё искать раздачу и паковать. Секунда тут мерила
    # скорость сети, а `<video>` на главной нет вовсе - страница показа только едет.
    if not _await_playback(ctx):
        return Result(6, "Сначала", False, None, "после «Сначала» первого кадра не было")
    current = float(ctx.page.eval_on_selector("video", "v => v.currentTime"))
    ok = current < 5.0
    return Result(6, "Сначала", ok, None, f"кнопка найдена, после клика currentTime={current:.1f}")


def _await_card(ctx: Ctx) -> bool:
    """Дождаться тела открытой карточки: кнопка показа есть - карточка доехала."""
    if not ctx.page.url.rsplit(ctx.base, 1)[-1].startswith("/card/"):
        return False
    # Признак «доехала» - кнопка показа ИЛИ непустое описание: у сериала кнопка ждёт
    # разбора раздачи дольше, чем справка, и судить только по ней значит терять
    # карточку, которая уже читается человеком.
    with contextlib.suppress(Exception):
        ctx.page.wait_for_function(
            "() => { const p = document.querySelector('[data-tc-play]');"
            " const d = document.querySelector('[data-tc-card-description]');"
            " return !!p || !!(d && d.innerText.trim()); }",
            timeout=_CARD_READY_WAIT,
        )
        return True
    return False


def _open_card_by_page(ctx: Ctx, title: str) -> str | None:
    """Открыть карточку ТЕМ ЖЕ путём, что и человек: поиск, плитка, карточка.

    Возвращает причину отказа строкой или ``None``, если карточка открыта и доехала.
    """
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    placeholder = ctx.english.get("web.search.placeholder", "")
    field = ctx.page.get_by_placeholder(placeholder, exact=True) if placeholder else None
    if field is None or field.count() == 0:
        return f"поле поиска не найдено: input[placeholder={placeholder!r}]"
    field.first.click()
    field.first.type(title)
    ctx.page.keyboard.press("Enter")
    with contextlib.suppress(Exception):
        ctx.page.locator(_LIVE_TILE).first.wait_for(state="visible", timeout=20000)
    if ctx.page.locator(_LIVE_TILE).count() == 0:
        return f"поиск {title!r} не дал ни одной плитки"
    ctx.page.locator(_LIVE_TILE).first.click()
    if not _await_card(ctx):
        return f"карточка {title!r} не доехала за {_CARD_READY_WAIT / 1000:.0f} с"
    return None


def check_7_series(ctx: Ctx, card_ok: bool) -> Result:
    """Сериал: список серий непуст, выбор s1e2 → закладка на s1e2.

    Карточку пункт открывает СВОЮ, а не донашивает ту, что осталась от пункта 3: там
    стоит фильм, у которого серий не бывает по устройству продукта.
    """
    if not card_ok:
        return Result(7, "Сериал", False, "пункт 3 (карточки нет)", "список серий негде искать")
    refusal = _open_card_by_page(ctx, _SERIES_TITLE)
    if refusal is not None:
        return Result(7, "Сериал", False, None, refusal)
    with contextlib.suppress(Exception):
        ctx.page.locator("[data-tc-episode]").first.wait_for(state="visible", timeout=30000)
    episodes = ctx.page.locator("[data-tc-episode]")
    count = episodes.count()
    if count == 0:
        detail = f"нет [data-tc-episode] в карточке {_SERIES_TITLE!r}"
        return Result(7, "Сериал", False, None, detail)
    # Искать надо по странице: `episodes` - это уже сами строки серий, и поиск ВНУТРИ
    # них не находит ничего никогда, каким бы верным ни был список.
    target = ctx.page.locator('[data-tc-episode="s1e2"]')
    if target.count() == 0:
        return Result(7, "Сериал", False, None, f"серий {count}, но s1e2 среди них нет")
    # Клик по серии - тоже старт показа, не иначе, чем кнопка «Играть» в пункте 4: без
    # `--play` он поднимал show мимо `allow_play` и мимо счётчика соседа. Тормоз тот же.
    guard = _playback_guard(7, "Сериал", ctx, True, "")
    if guard:
        return guard
    target.first.click()
    # Клик лишь КЛАДЁТ заказ: продукт ещё ищет раздачу и поднимает показ, и до тех пор
    # `/api/state` честно отвечает `null`. Полсекунды тут мерили скорость сети.
    season = episode = None
    began = time.monotonic()
    while time.monotonic() - began < _PLAY_START_WAIT / 1000.0:
        code, body = _get(ctx.base + "/api/state")
        if code == 200:
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(body)
                season, episode = payload.get("season"), payload.get("episode")
        if season is not None and episode is not None:
            break
        time.sleep(1.0)
    ok = season == 1 and episode == 2
    detail = f"серий {count}, выбран s1e2, /api/state season={season!r} episode={episode!r}"
    return Result(7, "Сериал", ok, None, detail)


def check_8_autoplay(ctx: Ctx, series_ok: bool) -> Result:
    """Автопереход: перемотка к концу → плашка с отсчётом → через 10 с следующая серия.

    🔴 Мерится на СЕРИАЛЕ, который поднял пункт 7, а не на фильме из пункта 4: следующей
    серии у фильма нет по устройству продукта, и плашка на нём не появится никогда
    (по живому замеру пункт держался красным на фильме и звал это дефектом).
    """
    guard = _playback_guard(8, "Автопереход", ctx, series_ok, "пункт 7 (сериал не поднялся)")
    if guard:
        return guard
    if not _await_playback(ctx):
        return Result(8, "Автопереход", False, None, "первого кадра серии так и не было")
    duration = float(ctx.page.eval_on_selector("video", "v => v.duration"))
    ctx.page.eval_on_selector("video", f"v => {{ v.currentTime = {max(duration - 15.0, 0.0)}; }}")
    began = time.monotonic()
    overlay = ctx.page.locator("[data-tc-next-episode]")
    # 🔴 Перемотка к концу попадает в НЕУПАКОВАННОЕ место, и продукт честно перезапускает
    # оттуда упаковку: до плашки надо ещё доиграть последние 15 секунд, а до них
    # дождаться первого куска. Двадцати секунд на это не хватает никогда - скрипт судил
    # раньше, чем продукт успевал ответить (по живому замеру). Срок тут тот же, что
    # продукт сам отводит на подъём показа, плюс те 15 с, которые надо доиграть.
    limit = _PLAY_START_WAIT / 1000.0 + 15.0
    while time.monotonic() - began < limit and overlay.count() == 0:
        ctx.page.wait_for_timeout(300)
    if overlay.count() == 0:
        at = _video(ctx, "v => v.currentTime")
        why = (
            f"плашка [data-tc-next-episode] не появилась за {limit:.0f} с; "
            f"позиция {at} из {duration:.1f}"
        )
        return Result(8, "Автопереход", False, None, why)
    before = _state(ctx)
    before_pair = (before.get("season"), before.get("episode"))
    ctx.page.wait_for_timeout(10_000)
    # 🔴 Планка - смена СЕРИИ, а не смена тела снимка: позиция тикает при любом показе,
    # и `before_body != after_body` зеленело бы и на перезапуске ТОЙ ЖЕ серии, то есть
    # на целиком сломанном автопереходе. Ждём, пока снимок назовёт другую пару
    # (сезон, серия): после отсчёта продукту ещё поднимать следующую серию, и судить
    # ровно через 10 с значило бы мерить скорость подъёма, а не переход.
    after: dict[str, Any] = {}
    after_pair = before_pair
    began = time.monotonic()
    while time.monotonic() - began < _PLAY_START_WAIT / 1000.0:
        after = _state(ctx)
        after_pair = (after.get("season"), after.get("episode"))
        if None not in after_pair and after_pair != before_pair:
            break
        ctx.page.wait_for_timeout(1000)
    ok = None not in after_pair and after_pair != before_pair
    detail = (
        f"плашка появилась; серия по /api/state: {before_pair} -> {after_pair}, сменилась: {ok}"
    )
    return Result(8, "Автопереход", ok, None, detail)


def check_9_on_tv(ctx: Ctx, play_ok: bool) -> Result:
    """На ТВ: приёмник играет тот же url, позиция растёт, muted, ползунок слушается."""
    guard = _playback_guard(9, "На ТВ", ctx, play_ok, "пункт 4 (показ не идёт)")
    if guard:
        return guard
    # Пункт 8 доводит серию до конца и уводит показ на следующую: до её первого кадра
    # `<video>` на странице есть, а играть ему ещё нечего.
    if not _await_playback(ctx):
        return Result(9, "На ТВ", False, None, "перед передачей на ТВ показ не идёт")
    label = ctx.english.get("web.player.play_on_tv", "")
    button = ctx.page.get_by_text(label, exact=True) if label else None
    if button is None or button.count() == 0:
        return Result(9, "На ТВ", False, None, f"кнопка {label!r} не найдена")
    _wake_panel(ctx)
    button.first.click()
    ctx.page.wait_for_timeout(2000)
    shown = _video(ctx, "v => v.muted")
    if shown is None:
        return Result(9, "На ТВ", False, None, "после «На ТВ» на странице нет `<video>`")
    muted = bool(shown)
    # 🔴 Каст поднимается не мгновенно: соединение с приёмником, LOAD и первый кадр на
    # телевизоре - это секунды. Скрипт спрашивал позицию через 2 с после нажатия и звал
    # ненаступившее отказом, хотя каст поднимался следом и играл потом ещё полчаса (по
    # живому замеру). Ждём, пока продукт НАЗОВЁТ приёмник, и только тогда меряем ход.
    took = _await_tv(ctx)
    tv_running = False
    grew_in = None
    volume_ok = False
    volume_detail = "каст не поднялся"
    url_ok = False
    url_detail = "каст не поднялся"
    if took is not None:
        before = _position(ctx)
        tv_running, grew_in = _await_position_growth(ctx, before)
        volume_ok, volume_detail = _volume_follows_page(ctx)
        url_ok, url_detail = _cast_url_matches(ctx)
    ok = muted and tv_running and volume_ok and url_ok
    waited = "не поднялся" if took is None else f"{took:.0f} с"
    grown = "не сдвинулась" if grew_in is None else f"за {grew_in:.1f} с"
    detail = (
        f"muted={muted}, каст поднялся за {waited}, позиция ТВ выросла {grown}; "
        f"url: {url_detail}; громкость: {volume_detail}"
    )
    return Result(9, "На ТВ", ok, None, detail)


def _cast_url_matches(ctx: Ctx) -> tuple[bool, str]:
    """Приёмник обязан играть ТОТ ЖЕ url, что играет вкладка - сверка обоих концов.

    🔴 До этой правки url не сверялся НИ РАЗУ: планка `muted and tv_running and
    volume_ok` зеленела и на касте чужой картины - позиция растёт и громкость
    слушается у любого показа. Вкладка называет свой поток ``TCPlayer._url``
    (``web/static/player.js``), а каст уходит приёмнику из ящика вкладки как есть
    (:func:`web.to_tv.to_tv` отдаёт ``SESSION.start`` тот ``url``, что лежит в
    ``/api/web/box``): равенство этих двух концов и есть «тот же url».
    """
    page_url = ctx.page.evaluate("() => (window.TCPlayer && TCPlayer._url) || ''")
    if not isinstance(page_url, str) or not page_url:
        return False, "вкладка свой url не назвала (TCPlayer._url пуст)"
    box_code, box_body = _get(ctx.base + "/api/web/box")
    box_url = ""
    if box_code == 200:
        with contextlib.suppress(json.JSONDecodeError):
            box_url = str(json.loads(box_body).get("url") or "")
    if not box_url:
        return False, f"GET /api/web/box -> {box_code}, url в ящике пуст"
    if page_url != box_url:
        return False, f"вкладка играет {page_url!r}, а на ТВ ушёл {box_url!r}"
    return True, f"вкладка и ТВ на одном url ({page_url[:80]})"


#: Сколько ждать, пока продукт назовёт каст своим: рукопожатие, LOAD и первый кадр.
_TV_WAIT: Final = 60.0

#: Худший промежуток между двумя непохожими докладами приёмника в замере TC-1177
#: 11-09-2026: 9, 20, 11 с (опрос `/api/state` раз в секунду во время каста на `.90`).
#: Берём максимум, а не среднее: именно следующий, ещё не приехавший доклад определяет,
#: сколько старая, но законная секунда может прожить в ящике при возврате на вкладку.
_RECEIVER_REPORT_CADENCE: Final = 20.0
#: После клика ждём один короткий кадр браузера: посадку снимает перехват сеттера в
#: самом клике, а это ожидание нужно только для проверки, что вкладка уже не на ТВ.
_PC_RETURN_SETTLE: Final = 2.0
#: Прибор ждёт, пока один доклад приёмника проживёт не меньше пяти секунд. На таком
#: возрасте сырая посадка в сам доклад промахивается заметно, а не прячется в шуме
#: доставки HTTP. 30 с = худшая каденция 20 с + требуемые 5 с + 5 с запаса на снимок.
_PC_STALE_AGE: Final = 5.0
_PC_STALE_WAIT: Final = _RECEIVER_REPORT_CADENCE + _PC_STALE_AGE + 5.0
#: Часы прибора узнают смену доклада с точностью этого опроса. Двух секунд достаточно
#: для этой погрешности и браузерного кадра, но не маскируют откат на пять секунд.
_PC_LANDING_TOLERANCE: Final = 2.0
_PC_REPORT_POLL: Final = 0.25

#: Шаг опроса позиции ТВ - тот же, каким сам продукт держит `current_time` живым
#: (``web.tv_session.POLL_SECONDS``): чаще спрашивать нечего, у приёмника ещё не
#: появится новое число.
_POSITION_POLL: Final = 2.0

#: Потолок ожидания честного сдвига позиции. Живой приёмник отдаёт позицию рывками, а
#: не плавно: независимый замер каденции (120 с опроса раз в секунду, 12 сдвигов) дал
#: шаг ~10.4 с при худшем промежутке 10.5 с; отдельный более долгий замер (окно 40 с)
#: поймал сдвиги через 3, затем через 10, затем через 24 с - худший из двух замеров.
#: Окно взято 40 с - в 1.6 раза больше худшего наблюдённого промежутка (24.5 с), а не
#: подогнано под то, что уже позеленело.
_POSITION_GROWTH_WAIT: Final = 40.0


def _await_position_growth(ctx: Ctx, before: float | None) -> tuple[bool, float | None]:
    """Ждать до :data:`_POSITION_GROWTH_WAIT`, пока позиция честно обгонит ``before``.

    Мера - «сдвинулась вперёд хотя бы раз за N секунд», а не одна пара до/после через
    фиксированную паузу: у живого приёмника отдача рывками (см. константу выше), и пара
    через 4 с из старой версии скрипта попадала на плато при работающем касте.
    """
    if before is None:
        return False, None
    began = time.monotonic()
    while time.monotonic() - began < _POSITION_GROWTH_WAIT:
        ctx.page.wait_for_timeout(int(_POSITION_POLL * 1000))
        after = _position(ctx)
        if after is not None and after > before:
            return True, time.monotonic() - began
    return False, None


def _state(ctx: Ctx) -> dict[str, Any]:
    """Снимок ``/api/state``; не ответил или не JSON - пустой словарь, а не исключение."""
    code, body = _get(ctx.base + "/api/state")
    if code != 200:
        return {}
    try:
        got = json.loads(body)
    except json.JSONDecodeError:
        return {}
    return got if isinstance(got, dict) else {}


def _position(ctx: Ctx) -> float | None:
    """Секунда показа из ``/api/state``; показа нет - ``null``, и это не ноль.

    🔴 ``null`` тут - штатный ответ продукта про несостоявшийся показ (:func:`hass.
    payload._nothing`), а не отсутствие поля. Скрипт читал его как ``0.0`` умолчанием
    ``dict.get`` и падал на сравнении двух ``None`` (живой прогон), унося весь пункт
    в «скрипт упал» вместо честного приговора.
    """
    at = _state(ctx).get("position")
    return float(at) if isinstance(at, int | float) else None


def _box_at(ctx: Ctx) -> tuple[float | None, bool | None, str]:
    """Секунда и признак каста из ящика вкладки, либо названная причина отказа.

    🔴 ``at`` тут НЕ живой доклад приёмника: :func:`write_web_box` во всём дереве зовут
    ровно два места - старт сеанса (``BrowserReceiver.play``) и сам возврат «На комп»
    (:mod:`web.to_web`, из ``TvSession.stop()``). Между ними ``at`` не обновляется вовсе,
    поэтому опрос этого поля на смену значения раньше давал мнимую «смену» в момент
    первого снимка, а не настоящий возраст доклада (см. :func:`_receiver_report`).
    Признак ``tv`` живой - его на каждый запрос заново считает
    :meth:`web.tv_session.TvSession.settle` - и годен для проверки «сейчас идёт каст».
    """
    code, body = _get(ctx.base + "/api/web/box")
    if code != 200:
        return None, None, f"GET /api/web/box -> {code}"
    try:
        box = json.loads(body)
    except json.JSONDecodeError as exc:
        return None, None, f"GET /api/web/box отдал не JSON: {exc}"
    if not isinstance(box, dict):
        return None, None, "GET /api/web/box отдал не объект"
    at = box.get("at")
    if not isinstance(at, int | float):
        return None, bool(box.get("tv")), f"at не число: {at!r}"
    return float(at), bool(box.get("tv")), ""


def _receiver_report(ctx: Ctx) -> tuple[float | None, str | None, str]:
    """Секунда и слово состояния из ``/api/state`` - тот же снимок, что живьём опрашивает
    ``TCPlayer._pollState`` (``web/static/player.js``) и что калибровала каденция TC-1177.

    В отличие от ``/api/web/box``.at (см. :func:`_box_at`), это поле приёмник обновляет
    рывками во время каста - тем же опросом, что держит :func:`hass.bridge.Bridge.state`
    живым. Это и есть независимый от вкладки источник для меры «доклад состарился».
    """
    snapshot = _state(ctx)
    if not snapshot:
        return None, None, "GET /api/state пуст или не ответил"
    at = snapshot.get("position")
    word = snapshot.get("state")
    word = word if isinstance(word, str) else None
    if not isinstance(at, int | float):
        return None, word, f"position не число: {at!r}"
    return float(at), word, ""


def _await_stale_receiver_report(ctx: Ctx) -> tuple[float | None, float | None, str | None, str]:
    """Дождаться известного прибору возраста последнего доклада ``/api/state``.

    Нужна именно увиденная СМЕНА ``position``: первый снимок мог лежать в приёмнике уже
    неизвестно сколько. После смены прибор меряет возраст своим ``monotonic()``, не
    ``TCPlayer._tvMark``. Если ТВ буферизуется, а его ``state`` ещё ``playing``,
    ``position`` не меняется и этот путь честно ожидает посадку на возраст-доведённой
    секунде - слово состояния уходит наружу, чтобы вызывающий решил, экстраполировать
    ли ход (граница TC-1185: буферизация при живом ``playing``).
    """
    began = time.monotonic()
    previous: float | None = None
    changed_at: float | None = None
    word: str | None = None
    while time.monotonic() - began < _PC_STALE_WAIT:
        _, on_tv, tv_problem = _box_at(ctx)
        if on_tv is not True:
            return None, None, None, tv_problem or f"box.tv={on_tv!r} до «На комп»"
        report, word, problem = _receiver_report(ctx)
        now = time.monotonic()
        if report is None:
            return None, None, None, problem
        if report != previous:
            previous = report
            changed_at = now
        elif changed_at is not None and now - changed_at >= _PC_STALE_AGE:
            return report, changed_at, word, ""
        ctx.page.wait_for_timeout(int(_PC_REPORT_POLL * 1000))
    return (
        None,
        None,
        None,
        f"доклад приёмника не прожил {_PC_STALE_AGE:.0f} с за {_PC_STALE_WAIT:.0f} с",
    )


def _watch_landing(ctx: Ctx, button: Any) -> None:
    """Запомнить первую секунду, присвоенную плёнке после клика «На комп».

    Снимок через две секунды после клика уже содержит ход самой плёнки. Перехват
    сеттера оставляет именно момент посадки, не подменяя его следующим кадром. Флаг
    взводит фаза capture того же клика, поэтому прежние доводки плёнки во время каста
    в пробу не попадают.
    """
    button.evaluate(
        """
        (button) => {
            const video = document.querySelector('video');
            if (!video) return;
            const descriptor = Object.getOwnPropertyDescriptor(
                HTMLMediaElement.prototype, 'currentTime');
            if (!descriptor || !descriptor.get || !descriptor.set) return;
            const state = { armed: false, landed: null, listener: null, video };
            state.listener = (event) => {
                if (button.contains(event.target)) state.armed = true;
            };
            document.addEventListener('click', state.listener, true);
            Object.defineProperty(video, 'currentTime', {
                configurable: true,
                get() { return descriptor.get.call(video); },
                set(value) {
                    if (state.armed && state.landed === null) state.landed = Number(value);
                    return descriptor.set.call(video, value);
                },
            });
            window.__tcAcceptanceLanding = state;
        }
        """
    )


def _landing(ctx: Ctx) -> float | None:
    """Снять и убрать временный наблюдатель посадки из вкладки."""
    landed = ctx.page.evaluate(
        """
        () => {
            const state = window.__tcAcceptanceLanding;
            if (!state) return null;
            document.removeEventListener('click', state.listener, true);
            delete state.video.currentTime;
            delete window.__tcAcceptanceLanding;
            return state.landed;
        }
        """
    )
    return float(landed) if isinstance(landed, int | float) else None


def _await_tv(ctx: Ctx) -> float | None:
    """Дождаться, пока каст поднимется; не поднялся за :data:`_TV_WAIT` - ``None``.

    🔴 Спрашивается ЯЩИК, а не ``/api/state``: поле ``tv`` снимка - это настройка
    ``config.tv`` (:func:`hass.bridge.Bridge.state`), она равна адресу приёмника и в
    простое, и до всякого нажатия. Скрипт ждал её и получал «поднялся за 0 с» всегда,
    в том числе тогда, когда ``POST /api/to-tv`` ответил отказом (живой прогон: код
    409, а пункт всё равно пошёл мерить ход). Ящик же отвечает ``tv: true`` ровно
    тогда, когда каст жив И держит ЭТОТ показ (:meth:`web.tv_session.TvSession.settle`).
    """
    began = time.monotonic()
    while time.monotonic() - began < _TV_WAIT:
        code, body = _get(ctx.base + "/api/web/box")
        if code == 200:
            with contextlib.suppress(json.JSONDecodeError):
                if json.loads(body).get("tv") is True:
                    return time.monotonic() - began
        ctx.page.wait_for_timeout(1000)
    return None


#: Сколько ждать, пока новый уровень громкости долетит до приёмника и обратно в
#: ``/api/state``: `hass.volume.Volume.set` пишет кэш сразу, опрос тут - подстраховка
#: на случай задержки самого HTTP-цикла страницы, а не на связь с телевизором.
_VOLUME_WAIT: Final = 6.0
#: Порог «это не шум округления, а настоящий сдвиг» для уровня 0..1.
_VOLUME_EPS: Final = 0.02


def _receiver_volume(ctx: Ctx) -> float | None:
    """Уровень громкости ПРИЁМНИКА 0..1 из ``/api/state`` - настоящий, а не браузерный.

    Поле идёт из :meth:`hass.volume.Volume.level`, а тот читает ``status.volume_level``
    настоящего Chromecast-соединения (:func:`hass.volume._connect`), поднятого тем же
    способом, что и показ. Другого способа честно снять громкость с `.90` со стороны
    скрипта нет - второе ``pychromecast``-соединение к тому же приёмнику рвёт чужой
    показ (см. докстроку модуля), а сам продукт этот путь уже открыл под ``/api/state``.
    """
    at = _state(ctx).get("volume")
    return float(at) if isinstance(at, int | float) else None


def _volume_follows_page(ctx: Ctx) -> tuple[bool, str]:
    """Ползунок громкости (стрелки ↑/↓, ``TCPlayer._volumeBy``) обязан двигать ПРИЁМНИК.

    На ТВ те же стрелки, что и без каста, шлют ``POST /api/control {cmd: volume}``
    вместо правки локального ``<video>.volume`` (``web/static/player.js``, решение 4);
    скрипт жмёт их и смотрит на ``/api/state``, а не на страницу - страница показывает
    то же самое число, которое сама и прислала.
    """
    before = _receiver_volume(ctx)
    if before is None:
        return False, "приёмник не отдал текущий уровень громкости"
    # У потолка/пола 0..1 нажатие в ту же сторону могло бы упереться в клип - берём
    # направление, где заведомо есть куда сдвинуться.
    key = "ArrowUp" if before <= 0.5 else "ArrowDown"
    want_more = key == "ArrowUp"
    ctx.page.keyboard.press(key)
    ctx.page.keyboard.press(key)
    began = time.monotonic()
    after = before
    while time.monotonic() - began < _VOLUME_WAIT:
        ctx.page.wait_for_timeout(500)
        seen = _receiver_volume(ctx)
        if seen is not None:
            after = seen
            moved = (after - before) if want_more else (before - after)
            if moved >= _VOLUME_EPS:
                break
    moved = (after - before) if want_more else (before - after)
    ok = moved >= _VOLUME_EPS
    direction = "громче" if want_more else "тише"
    detail = f"{before:.2f} -> {after:.2f} ({direction}, нажат {key})"
    return ok, detail


def check_10_on_pc(ctx: Ctx, on_tv_ok: bool) -> Result:
    """На комп: приборными часами сверить посадку с состаренным докладом ТВ."""
    if not on_tv_ok:
        return Result(10, "На комп", False, "пункт 9 (на ТВ не снят)", "возвращать не от чего")
    label = ctx.english.get("web.player.back_to_browser", "")
    button = ctx.page.get_by_text(label, exact=True) if label else None
    if button is None or button.count() == 0:
        return Result(10, "На комп", False, None, f"кнопка {label!r} не найдена")
    # Второй pychromecast к одному приёмнику способен перебить чужой каст. Поэтому
    # прибор сам засекает возраст сменившегося доклада ``/api/state`` и нажимает на
    # известной его старости. Это не часы TCPlayer и не проверка продукта его же числом.
    receiver_at, changed_at, word, report_problem = _await_stale_receiver_report(ctx)
    if receiver_at is None or changed_at is None:
        return Result(10, "На комп", False, None, report_problem)
    _watch_landing(ctx, button.first)
    _wake_panel(ctx)
    report_age = time.monotonic() - changed_at
    # TCPlayer._tvPosition (web/static/player.js) экстраполирует ход только пока
    # `state.state === 'playing'` - на паузе/буферизации отдаёт доклад как есть.
    playing = word == "playing"
    expected = receiver_at + report_age if playing else receiver_at
    button.first.click()
    ctx.page.wait_for_timeout(int(_PC_RETURN_SETTLE * 1000))
    shown = _video(ctx, "v => v.muted")
    if shown is None:
        return Result(10, "На комп", False, None, "после «На комп» на странице нет `<video>`")
    muted = bool(shown)
    landed = _landing(ctx)
    _, still_on_tv, box_problem = _box_at(ctx)
    landing_gap = abs(landed - expected) if landed is not None else None
    ok = (
        not muted
        and still_on_tv is False
        and landed is not None
        and landing_gap is not None
        and landing_gap <= _PC_LANDING_TOLERANCE
    )
    detail = (
        f"muted={muted}, box.tv={still_on_tv}; доклад приёмника={receiver_at} "
        f"(state={word!r}), возраст по часам прибора={report_age:.2f} с; "
        f"ожидаемая посадка={expected:.2f}, "
        f"посадка вкладки={landed}, промах={landing_gap}; допуск ±{_PC_LANDING_TOLERANCE:.1f} с "
        f"(доклад состарен минимум на {_PC_STALE_AGE:.0f} с, потолок ожидания "
        f"{_PC_STALE_WAIT:.0f} с); "
        f"{box_problem or 'ящик прочитан'}"
    )
    return Result(10, "На комп", ok, None, detail)


#: Порог сторожа TC-1124. Живой замер (`scripts/leftprobe.py`, до и после правки):
#: хвост показа после ухода со страницы держался 8.3 с после правки против 60.2 с до
#: неё, а окно `state == "playing"` при неподвижной позиции - 1.1 с против 53.6 с.
#: 15 с - больше чем вдвое над честным `left_after=5.0`, но меньше половины старого
#: 60-секундного молчания: откат `left_after` (на 0.0 или на что-то около `gone_after`)
#: непременно перескакивает порог, а сама правка - никогда.
_LEAVE_TEARDOWN_LIMIT: Final = 15.0


def check_20_leave_tears_down(ctx: Ctx, prev_ok: bool) -> Result:
    """Сторож TC-1124: закрытая (ушедшая) вкладка разбирает показ за секунды, не за 60.

    Пункт обязан краснеть, если `left_after` откатить: без него уход со страницы ловит
    только полное молчание (`gone_after=60.0`), и показ ещё почти минуту держит
    полосу упаковки занятой, а карточку плеера - неверно бегущей (TC-1124).
    """
    guard = _playback_guard(20, "Уход", ctx, prev_ok, "пункт 10 (на компе показ не поднят)")
    if guard:
        return guard
    before_code, before_body = _get(ctx.base + "/api/state")
    # `page.reload()` уходит с текущего адреса и возвращается на него же: тот же путь,
    # каким уход со страницы ловился в `leftprobe.py` (`pagehide`) - вкладку не закрываем
    # взаправду, чтобы страница осталась пригодной, если этот пункт не последний.
    ctx.page.reload(wait_until="load", timeout=15000)
    began = time.monotonic()
    after_code: int | None = None
    after_body: bytes | None = None
    elapsed: float | None = None
    while time.monotonic() - began < _LEAVE_TEARDOWN_LIMIT:
        after_code, after_body = _get(ctx.base + "/api/state")
        if after_code == 200:
            with contextlib.suppress(json.JSONDecodeError):
                if json.loads(after_body).get("state") != "playing":
                    elapsed = time.monotonic() - began
                    break
        time.sleep(0.5)
    ok = elapsed is not None
    was = (
        before_body.decode("utf-8", "replace")[:120] if before_code == 200 else f"код {before_code}"
    )
    now = (
        after_body.decode("utf-8", "replace")[:120]
        if after_code == 200 and after_body is not None
        else f"код {after_code}"
    )
    took = (
        f"{elapsed:.1f} с"
        if elapsed is not None
        else f"не разобрался за {_LEAVE_TEARDOWN_LIMIT:.0f} с"
    )
    detail = f"до ухода: {was}; после ухода ({took}): {now}"
    return Result(20, "Уход", ok, None, detail)


def _focus_of(ctx: Ctx) -> dict[str, Any]:
    """Что сейчас в фокусе: подпись для отчёта и три приметы, по которым выбирают клавишу."""
    found: dict[str, Any] = ctx.page.evaluate(
        "() => { const e = document.activeElement;"
        " if (!e) return {sig: 'null', play: false, tile: false, field: false};"
        " return {sig: e.tagName + '#' + (e.id || '-')"
        "   + (e.hasAttribute('data-tc-play') ? '!play' : '')"
        "   + (e.hasAttribute('data-tc-tile') ? '!tile' : ''),"
        "  play: e.hasAttribute('data-tc-play'), tile: e.hasAttribute('data-tc-tile'),"
        "  field: e.tagName === 'INPUT'}; }"
    )
    return found


def _dpad_key(focus: dict[str, Any], stuck: bool) -> str:
    """Клавиша, которую нажал бы человек с пультом, глядя на нынешний фокус.

    🔴 Не «Right, Down, Enter по кругу»: заводной порядок клавиш уводит фокус С кнопки
    «Играть», на которую сам же и привёл (замер 07-09-2026: фокус вставал на кнопку
    четвёртым нажатием и уходил пятым, показ не стартовал ни разу за 12). Скрипт мерил
    бы тогда свой круг клавиш, а не путь, который проходит зритель.
    """
    if focus["play"] or focus["tile"]:
        return "Enter"
    # Из поля ввода вправо уезжает КАРЕТКА, а не фокус: наружу поле отпускает вниз.
    # Так же и упёршийся в край строки: следующая полка - под ней.
    return "ArrowDown" if focus["field"] or stuck else "ArrowRight"


def _focus_visible(ctx: Ctx) -> tuple[bool, str]:
    """Виден ли фокус на кадре ПРЯМО СЕЙЧАС: узел в поле зрения и его маркер нарисован.

    Кадры в ``--shots`` разбирал глазами человек, а пункт зеленел не глядя на них.
    Судится ПОКРАСКА, а не класс: ``is-lit`` без стиля не виден никому. Приметы
    видимого фокуса из ``web/static/style.css``: контур (``outline``) на самом узле
    или на рамке плитки ``.tc-tile-frame``, разворот ``transform`` у плитки, заливка
    фона у строк (серии, выпадайки), а у поля ввода - каретка и кислотная линия
    снизу, её видно само по себе.
    """
    found: dict[str, Any] = ctx.page.evaluate(
        "() => {"
        " const e = document.activeElement;"
        " if (!e || e === document.body) return {visible: false, why: 'фокуса нет'};"
        " const r = e.getBoundingClientRect();"
        " const inView = r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0"
        "   && r.top < window.innerHeight && r.left < window.innerWidth;"
        " if (!inView) return {visible: false, why: 'фокус вне кадра'};"
        # Прозрачность - только четвёртый канал: кислотный `rgb(198, 255, 0)` тоже
        # кончается на «, 0)», и без `rgba` его контур считался ненарисованным.
        " const alpha0 = /^rgba\\(.*,\\s*0(?:\\.0+)?\\s*\\)$/;"
        " const painted = (s) => s.outlineStyle !== 'none'"
        "   && parseFloat(s.outlineWidth) > 0 && !alpha0.test(s.outlineColor);"
        " const cs = getComputedStyle(e);"
        " const frame = e.querySelector ? e.querySelector('.tc-tile-frame') : null;"
        " if (painted(cs)) return {visible: true, why: 'контур'};"
        " if (frame && painted(getComputedStyle(frame)))"
        "   return {visible: true, why: 'контур рамки плитки'};"
        " if (cs.transform !== 'none') return {visible: true, why: 'разворот'};"
        " if (e.tagName === 'INPUT') return {visible: true, why: 'поле ввода (каретка)'};"
        " if ((e.classList.contains('is-lit') || e.closest('.is-lit'))"
        "   && !alpha0.test(cs.backgroundColor)"
        "   && cs.backgroundColor !== 'rgba(0, 0, 0, 0)')"
        "   return {visible: true, why: 'заливка'};"
        " return {visible: false, why: 'маркер фокуса не нарисован'}; }"
    )
    return bool(found["visible"]), str(found["why"])


def check_11_arrows(ctx: Ctx) -> Result:
    """Стрелки: от поля поиска до старта показа за ≤12 нажатий, фокус виден на кадре."""
    # Полосу упаковки тут НЕ освобождают нарочно: предыдущие пункты оставляют показ, и
    # продукт нарочно велит новой «Играть» СНИМАТЬ идущий. Освободить её скриптом
    # значило бы снять с продукта ровно то требование, ради которого пункт и меряет
    # старт показа.
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    placeholder = ctx.english.get("web.search.placeholder", "")
    field = ctx.page.get_by_placeholder(placeholder, exact=True) if placeholder else None
    if field is None or field.count() == 0:
        detail = f"поле поиска не найдено: input[placeholder={placeholder!r}] нет в DOM"
        return Result(11, "Стрелки", False, None, detail)
    field.first.focus()
    ctx.shots.mkdir(parents=True, exist_ok=True)
    steps: list[str] = []
    started = False
    reached_play = False
    stuck = False
    unseen: list[str] = []
    # `allow_play` - единственная дверь к показу и здесь: `_dpad_key` зовёт Enter, едва
    # фокус встал на «Играть», а Enter по ней и есть старт. Раньше от этого прикрывал
    # только счётчик нажатий (11 без `--play` против 12) - но фокус доходил до кнопки
    # и раньше 11-го нажатия (замер 07-09-2026: на 4-5-м), и следующая итерация цикла
    # нажимала Enter по ней вслепую, не спросив `allow_play`. Тормоз теперь стоит там,
    # где Enter решает: перед нажатием, а не в числе допустимых нажатий.
    limit = 12
    for i in range(limit):
        was = _focus_of(ctx)
        if was["play"]:
            reached_play = True
            if not ctx.allow_play:
                steps.append(f"{i + 1}:стоп(фокус на «Играть», --play не задан)")
                break
        key = _dpad_key(was, stuck)
        ctx.page.keyboard.press(key)
        ctx.page.wait_for_timeout(150)
        # Enter на плитке уводит на карточку, а она едет по сети. Стрелка по скелету
        # никуда не ведёт не потому, что навигация плоха, а потому, что кнопок ещё нет:
        # мера пункта - НАЖАТИЯ, а не миллисекунды, и ждать тело тут честно.
        _await_card(ctx)
        ctx.page.screenshot(path=str(ctx.shots / f"arrow-{i:02d}.png"))
        active = _focus_of(ctx)
        # Кадр пишется не для архива, а для суда: «фокус виден на кадре» - планка
        # пункта, и шаг, на котором маркер фокуса не нарисован, красит пункт целиком.
        # Enter на «Играть» уводит страницу на /play, и activeElement там - BODY:
        # навигация кончилась, фокуса на странице больше нет и судить его нечего.
        if "/play" not in ctx.page.url:
            visible, why = _focus_visible(ctx)
            if not visible:
                unseen.append(f"{i + 1}({active['sig']}: {why})")
        stuck = key == "ArrowRight" and active["sig"] == was["sig"]
        steps.append(f"{i + 1}:{key}->{active['sig']}")
        reached_play = reached_play or bool(active["play"])
        video = ctx.page.locator("video")
        if video.count() and float(ctx.page.eval_on_selector("video", "v => v.currentTime")) > 0:
            started = True
            break
    # Двенадцатое нажатие лишь КЛАДЁТ заказ: до первого кадра продукту ещё искать
    # раздачу и паковать. Судить старт внутри той же итерации значит судить сеть.
    if ctx.allow_play and not started and reached_play:
        started = _await_playback(ctx)
    ok = (started if ctx.allow_play else reached_play) and not unseen
    goal = "показ стартовал" if ctx.allow_play else "фокус дошёл до «Играть»"
    got = started if ctx.allow_play else reached_play
    stop_note = "" if ctx.allow_play else " (--play не задан: пункт судится по фокусу)"
    sight = (
        f"фокус виден на всех {len(steps)} кадрах"
        if not unseen
        else (f"фокус НЕ виден на кадрах: {', '.join(unseen)}")
    )
    detail = f"нажатий {len(steps)}/{limit}, кадры в {ctx.shots}, {goal}: {got}{stop_note}; {sight}"
    return Result(11, "Стрелки", ok, None, "; ".join(steps) + " | " + detail)


def check_12_franchise(base: str) -> Result:
    """Франшиза: все 10 полок родни непусты - полем ``related`` карточки.

    Шов родни на веб-поверхности один: карточка картины отдаёт полку в ``related``
    (:mod:`web.related_lookup`). Отдельного маршрута франшизы нет и не задумано, поэтому
    скрипт идёт тем же путём, что и страница: поиск по названию даёт ключ, ключ даёт
    карточку. Родня приезжает фоном, значит ждать её надо по ``X-Torrcast-Partial``.

    Планка - ДЕСЯТЬ из десяти, а не восемь. Пока продукт держал пустую полку у «Чужого»
    (TC-1163), допуск в две франшизы делал пункт зелёным ровно на том дефекте, ради
    которого пункт и заведён: полка родни пуста либо у всех, либо ни у кого, и «две
    пустые - ещё не беда» неоткуда взять, кроме как из состояния дерева. Продукт дал
    десять из десяти (стенд `.104`, 10-09-2026, три прогона подряд), и допуск снят.
    Пустая полка называется в детали ПОИМЁННО: считать нули в списке размеров глазами
    человеку не с руки.
    """
    non_empty = 0
    sizes: list[str] = []
    empty: list[str] = []
    for title in _FRANCHISE_TITLES:
        card = _card_of(base, title)
        kin = card.get("related") if isinstance(card, dict) else None
        size = len(kin) if isinstance(kin, list) else 0
        non_empty += size > 0
        short = title.split()[0]
        sizes.append(f"{short}={size if isinstance(kin, list) else 'нет'}")
        if size == 0:
            empty.append(short)
    ok = non_empty == len(_FRANCHISE_TITLES)
    detail = f"непустых полок {non_empty} из {len(_FRANCHISE_TITLES)}; " + ", ".join(sizes)
    if empty:
        detail += f"; пусто у франшиз: {', '.join(empty)}"
    return Result(12, "Франшиза", ok, None, detail)


def _page_assets(base: str) -> tuple[list[str], list[str], list[str]]:
    """Скрипты и стили, которые страница называет сама; третьим списком - недоехавшее."""
    code, body = _get(base + "/")
    if code != 200:
        return [], [], [f"GET / -> {code}"]
    shell = body.decode("utf-8", "replace")
    scripts = [one for one in _PAGE_SCRIPT_RE.findall(shell) if not _VENDORED_RE.search(one)]
    styles = [one for one in _PAGE_STYLE_RE.findall(shell) if not _VENDORED_RE.search(one)]
    return scripts, styles, []


def check_13_texts(base: str) -> Result:
    """Тексты: нет литералов человеку в static/*, все ключи страницы в каталоге, ru = набор.

    Файлы берутся из разметки самой страницы, а не из перечня имён внутри пункта. До
    10-09-2026 перечень был `app.js`/`player.js` - два файла из четырнадцати, которые
    грузит `index.html`, и три ключа `say()` из тридцати девяти. Одиннадцать скриптов с
    надписями человеку (`card.js`, `home.js`, `player-screens.js` и прочие) проезжали
    мимо сторожа, при том что название пункта обещает `static/*` целиком: ключ, забытый
    в каталоге, зеленел бы вплоть до пустого места на экране.

    Файл, который страница называет, а сервер не отдаёт, - отказ пункта, а не тихий ноль
    находок: «литералов не нашлось, потому что читать было нечего» и «литералов нет» с
    вывода прибора выглядят одинаково, и различить их обязан прибор, а не человек.

    ⚠️ Грепом, а не разбором AST (см. шапку модуля).
    """
    en_code, en_body = _get(base + "/api/phrases")
    ru_code, ru_body = _get(base + "/api/phrases?lang=ru")
    english = json.loads(en_body) if en_code == 200 else {}
    russian = json.loads(ru_body) if ru_code == 200 else {}
    same_keys = en_code == 200 and ru_code == 200 and set(english) == set(russian)

    scripts, styles, unreachable = _page_assets(base)
    referenced: set[str] = set()
    suspects: list[str] = []
    for path in scripts:
        code, body = _get(base + path)
        if code != 200:
            unreachable.append(f"GET {path} -> {code}")
            continue
        text = body.decode("utf-8", "replace")
        referenced |= set(_SAY_KEY_RE.findall(text))
        name = path.rsplit("/", 1)[-1]
        for lineno, line in enumerate(text.splitlines(), start=1):
            for match in _STRING_RE.finditer(line):
                if _is_prose(match.group(2)):
                    suspects.append(f"{name}:{lineno}:{match.group(2)!r}")
    missing_keys = sorted(referenced - set(english))

    css_suspects: list[str] = []
    for path in styles:
        code, body = _get(base + path)
        if code != 200:
            unreachable.append(f"GET {path} -> {code}")
            continue
        name = path.rsplit("/", 1)[-1]
        for lineno, line in enumerate(body.decode("utf-8", "replace").splitlines(), start=1):
            for match in _CONTENT_PROP_RE.finditer(line):
                if any(ch.isalpha() for ch in match.group(2)):
                    css_suspects.append(f"{name}:{lineno}:{match.group(2)!r}")

    ok = (
        same_keys
        and bool(scripts)
        and not unreachable
        and not missing_keys
        and not suspects
        and not css_suspects
    )
    detail = (
        f"EN ключей {len(english)} (код {en_code}), RU ключей {len(russian)} (код {ru_code}), "
        f"наборы {'совпадают' if same_keys else 'РАСХОДЯТСЯ'}; "
        f"осмотрено файлов страницы: {len(scripts)} js + {len(styles)} css"
        + (f", НЕ ПРОЧИТАНО: {'; '.join(unreachable)}" if unreachable else "")
        + f"; ключей из них {len(referenced)}, вне каталога: {missing_keys or 'нет'}; "
        f"JS-литералов человеку: {len(suspects)} {suspects}; "
        f"CSS content-литералов: {len(css_suspects)} {css_suspects}"
    )
    return Result(13, "Тексты", ok, None, detail)


#: Потолок ожидания гейта. Штатный полный прогон - около 400 с (см. `scripts/test-gate`),
#: срок взят с двойным запасом над ним, а не подогнан: дальше этого гейт не «медленный»,
#: а вставший (например, на системном приглашении пароля, которое `capture_output`
#: прячет в трубу), и пункт обязан покраснеть и назвать, на чём гейт стоял.
_GATE_WAIT: Final = 900.0


def check_14_gate(repo: Path) -> Result:
    """Гейт: полный `scripts/test-gate` зелёный на холодном венве, там, где лежит репа."""
    script = repo / "scripts" / "test-gate"
    if not script.exists():
        detail = f"{script} не найден - на этом хосте гейт не гоняется отсюда"
        return Result(14, "Гейт", False, f"нет репозитория по --repo {repo}", detail)
    missing = [tool for tool in ("jq", "uv", "ffmpeg") if shutil.which(tool) is None]
    if missing:
        # Скрипт живёт на машине с браузером, а гейт - на машине с деревом и
        # инструментами. Красный тут значил бы «продукт сломан», хотя сломана площадка.
        detail = f"на этой машине нет {', '.join(missing)}: гейт гоняется там, где дерево"
        return Result(14, "Гейт", False, "гейт нечем гонять с этого хоста", detail)
    began = time.monotonic()
    # 🔴 `stdin=DEVNULL` обязателен: гейт, упёршийся в приглашение пароля (systemctl,
    # sudo), с унаследованным stdin ждёт ввод, который некому набрать, а
    # `capture_output=True` прячет само приглашение в трубу - прибор вставал намертво
    # и не давал снять приёмку вообще. Срок - вторая половина той же страховки.
    try:
        proc = subprocess.run(
            [str(script)],
            cwd=str(repo),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=_GATE_WAIT,
        )
    except subprocess.TimeoutExpired as hung:
        spent = time.monotonic() - began
        out_text = (
            hung.stdout.decode("utf-8", "replace")
            if isinstance(hung.stdout, bytes)
            else str(hung.stdout or "")
        )
        err_text = (
            hung.stderr.decode("utf-8", "replace")
            if isinstance(hung.stderr, bytes)
            else str(hung.stderr or "")
        )
        tail = "\n".join((out_text + err_text).splitlines()[-25:])
        detail = (
            f"гейт не кончился за {spent:.0f} с (срок {_GATE_WAIT:.0f} с); "
            f"стоял на:\n{tail or 'молчал - не напечатал ни строки'}"
        )
        return Result(14, "Гейт", False, None, detail)
    spent = time.monotonic() - began
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
    ok = proc.returncode == 0
    detail = f"rc={proc.returncode} за {spent:.1f} с; хвост:\n{tail}"
    return Result(14, "Гейт", ok, None, detail)


#: Карточка глазами человека (пункты 28-31): загруженная картинка обложки, имя и описание
#: ТЕКСТОМ. Скелет описания несёт ту же метку ``data-tc-card-description``, но пуст.
_CARD_LOOK: Final = """() => {
  const since = window.__tcClickAt == null ? null : (performance.now() - window.__tcClickAt) / 1000;
  const card = document.querySelector('[data-tc-card]');
  if (!card) return { since, poster: false, title: '', desc: '' };
  const img = card.querySelector('.tc-detail-poster img.tc-tile-art-img');
  const desc = card.querySelector('[data-tc-card-description]');
  const title = card.querySelector('.tc-title-detail');
  return {
    since,
    poster: !!(img && img.complete && img.naturalWidth > 0),
    title: title ? title.textContent.trim() : '',
    desc: desc && !desc.classList.contains('tc-detail-skel') ? desc.textContent.trim() : '',
  };
}"""
#: Номер последней плитки главной, чью середину человек видит: она в окне и под ней сама
#: плитка; нет такой - ``-1``. Середина, а не вся плитка: ряд полки обрезан краем окна, и
#: правило «целиком» оставляло три плитки полки истории, уже согретые. Проверка попадания:
#: крайнюю плитку ряда накрывает поле у края полки (``tc-shelf-safe``), и клик уходил в него.
_PICK_TILE: Final = """sel => {
  let last = -1;
  document.querySelectorAll(sel).forEach((tile, i) => {
    const b = tile.getBoundingClientRect();
    const x = b.left + b.width / 2;
    const y = b.top + b.height / 2;
    if (!(b.width > 0 && x >= 0 && y >= 0 && x < innerWidth && y < innerHeight)) return;
    const e = document.elementFromPoint(x, y);
    if (e && e.closest('[data-tc-tile]') === tile) last = i;
  });
  return last;
}"""
#: Точка плитки, ближайшая к её середине, в которую клик попадёт в саму плитку; ``null``,
#: если такой нет.
_HIT_POINT: Final = """tile => {
  const b = tile.getBoundingClientRect();
  const cx = b.left + b.width / 2;
  const cy = b.top + b.height / 2;
  const points = [];
  for (let i = 1; i < 8; i++) {
    for (let j = 1; j < 8; j++) {
      points.push([b.left + (b.width * i) / 8, b.top + (b.height * j) / 8]);
    }
  }
  points.sort((p, q) => Math.hypot(p[0] - cx, p[1] - cy) - Math.hypot(q[0] - cx, q[1] - cy));
  for (const [x, y] of points) {
    if (x < 0 || y < 0 || x >= innerWidth || y >= innerHeight) continue;
    const e = document.elementFromPoint(x, y);
    if (e && e.closest('[data-tc-tile]') === tile) return [x, y];
  }
  return null;
}"""
#: Запросы плиток с картинкой, чья середина за краем окна: их не грел никто, как у
#: владельца, долиставшего полку. Берутся первая, средняя и последняя - врозь, чтобы
#: прогрев соседей одной, пока до неё листали, не согрел следующую.
_COLD_TILES: Final = """sel => {
  const out = [];
  document.querySelectorAll(sel).forEach(tile => {
    const b = tile.getBoundingClientRect();
    const x = b.left + b.width / 2;
    const y = b.top + b.height / 2;
    const off = b.width > 0 && (x < 0 || y < 0 || x > innerWidth || y > innerHeight);
    const q = tile.dataset.tcWarm || '';
    if (off && q && tile.querySelector('img.tc-tile-art-img') && !out.includes(q)) out.push(q);
  });
  return out.length <= 3 ? out : [out[0], out[out.length >> 1], out[out.length - 1]];
}"""
#: Что под курсором в точке ``[x, y]``: запрос плитки или тег с классом того, что вместо неё.
_UNDER: Final = """([x, y]) => {
  const e = document.elementFromPoint(x, y);
  const t = e && e.closest('[data-tc-tile]');
  if (t) return t.dataset.tcWarm || 'плитка';
  return e ? e.tagName.toLowerCase() + '.' + e.className : 'ничего';
}"""
_TILE_BY_QUERY: Final = """([sel, q]) =>
  [...document.querySelectorAll(sel)].findIndex(tile => tile.dataset.tcWarm === q)"""
_TILE_ART: Final = """tile => {
  const img = tile.querySelector('img.tc-tile-art-img');
  return !!(img && img.complete && img.naturalWidth > 0);
}"""
#: Плитки выдачи: имя и год, как их различает человек, и загрузилась ли картинка.
#: ``textContent``, а не ``innerText``: второй отдаёт буквы уже после ``text-transform``.
_TILE_LOOKS: Final = """tiles => tiles.map(tile => {
  const img = tile.querySelector('img.tc-tile-art-img');
  const cap = tile.querySelector('.tc-caption');
  const year = tile.querySelector('.tc-tile-year');
  return { title: cap ? cap.textContent.trim() : '', year: year ? year.textContent.trim() : '',
           art: !!(img && img.complete && img.naturalWidth > 0) };
})"""
_PARTS: Final = {"poster": "обложка", "title": "имя", "desc": "описание"}
#: «Открылась сразу»: обложка, имя и описание - не позже секунды от клика.
_AT_ONCE: Final = 1.0
#: N холодной карточки: дольше этого человек не ждёт описание (или слова «нет описания»)
#: у картины, которую никто не грел. Холодный ``/api/card`` доходит до 11.7 с (замер
#: пункта 22), и ещё 6 с описание стоит скелетом (``card.js``, ``_PATIENCE``).
_COLD_CARD: Final = 20.0
#: Сколько человек смотрит на главную с курсором на плитке, прежде чем кликнуть. До
#: починки к 15-й секунде после загрузки было согрето 3 из 8 видимых плиток (стенд
#: ``.104``, окно 1920x1080), и последняя видимая открывалась холодной за 5.4 с.
_AIM_WAIT: Final = 15.0
#: Окно счёта ``GET /api/card`` после клика и потолок в нём: первый ответ и один добор.
#: Журнал прода 11-09-2026 показывал 4-6 запросов на одну картину.
_GET_WINDOW: Final = 12.0
_GETS_AT_MOST: Final = 2
#: Выдача пункта 30 и срок, за который её круг обязан кончиться.
_MATRIX: Final = "матрица"
_SEARCH_SETTLE: Final = 60.0
#: Каст с карточки (пункт 29, только ``--play``): подъём холодного роя.
_CAST_WAIT: Final = 150.0


#: Часы пунктов 28 и 31 идут от клика, который ПОЛУЧИЛА страница, а не от вызова
#: ``click()``: тот сперва ждёт, пока плитка перестанет ехать (прокрутка, рост ряда), и
#: это ожидание прибор записывал карточке (1.48 с при оболочке, вставшей за 0.06 с).
_ARM_CLICK: Final = """() => {
  window.__tcClickAt = null;
  document.addEventListener('click', () => { window.__tcClickAt = performance.now(); },
    { capture: true, once: true });
}"""


class _CardGets:
    """Запросы страницы к ``/api/card/``: сколько ушло и когда пришёл первый ответ."""

    def __init__(self) -> None:
        self.began = time.monotonic()
        self.asked: list[str] = []
        self.answered_at: float | None = None

    def request(self, request: Any) -> None:
        if "/api/card/" in request.url:
            self.asked.append(request.url)

    def response(self, response: Any) -> None:
        if "/api/card/" in response.url and self.answered_at is None:
            self.answered_at = time.monotonic()

    def first_answer(self, clicked: float | None) -> float | None:
        """Секунды от клика до первого ответа; клика или ответа не было - ``None``."""
        if clicked is None or self.answered_at is None:
            return None
        return round(self.answered_at - clicked, 2)


@contextlib.contextmanager
def _counting_gets(ctx: Ctx) -> Iterator[_CardGets]:
    """Считать ``GET /api/card/`` страницы, пока открыт блок; отсчёт - от входа в него."""
    gets = _CardGets()
    ctx.page.on("request", gets.request)
    ctx.page.on("response", gets.response)
    try:
        yield gets
    finally:
        ctx.page.remove_listener("request", gets.request)
        ctx.page.remove_listener("response", gets.response)


def _watch_card(
    ctx: Ctx, ceiling: float
) -> tuple[dict[str, float | None], dict[str, Any], float | None]:
    """Секунды от клика (:data:`_ARM_CLICK`) до обложки, имени и описания карточки,
    последний взгляд на неё и миг клика на часах прибора; клика страница не получила -
    ``None``, и часы идут от входа сюда."""
    at: dict[str, float | None] = dict.fromkeys(_PARTS)
    began = time.monotonic()
    clicked: float | None = None
    while True:
        look = ctx.page.evaluate(_CARD_LOOK) or {}
        now = time.monotonic()
        since = look.get("since")
        if since is not None and clicked is None:
            clicked = now - float(since)
        spent = round(now - (began if clicked is None else clicked), 2)
        for part in at:
            if at[part] is None and look.get(part):
                at[part] = spent
        if None not in at.values() or spent >= ceiling:
            return at, look, clicked
        ctx.page.wait_for_timeout(50)


def _said_at(at: dict[str, float | None]) -> str:
    return ", ".join(
        f"{_PARTS[part]} {'нет' if spent is None else f'{spent:.2f} с'}"
        for part, spent in at.items()
    )


def _home(ctx: Ctx) -> None:
    """Свежая главная, как её открывает человек: до первой живой плитки полки."""
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    with contextlib.suppress(Exception):
        ctx.page.locator(_LIVE_TILE).first.wait_for(
            state="visible", timeout=_HOME_TILES_WAIT * 1000
        )


def _home_tile(ctx: Ctx) -> Any:
    """Последняя видимая плитка свежей главной (:data:`_PICK_TILE`); нет такой - ``None``.

    Главная долистана на полэкрана вниз, как её листает человек до полки новинок: без
    этого последней видимой оставалась плитка «Продолжить», а её прогрев берёт первой.
    """
    _home(ctx)
    ctx.page.evaluate("() => window.scrollBy(0, innerHeight / 2)")
    ctx.page.wait_for_timeout(1000)
    index = ctx.page.evaluate(_PICK_TILE, _LIVE_TILE)
    return ctx.page.locator(_LIVE_TILE).nth(index) if index >= 0 else None


def _middle(ctx: Ctx, tile: Any) -> tuple[float, float]:
    """Куда человек жмёт по плитке сейчас, а не когда её выбрал (:data:`_HIT_POINT`).

    Нет точки попадания - середина ВИДНОЙ части: плитка у нижнего края окна после роста
    ряда свешивается за край, и клик в середину всей плитки уходил мимо окна.
    """
    point = tile.evaluate(_HIT_POINT)
    if point:
        return float(point[0]), float(point[1])
    frame = tile.bounding_box() or {"x": 0, "y": 0, "width": 0, "height": 0}
    size = ctx.page.viewport_size or {"width": 0, "height": 0}
    left, right = max(frame["x"], 0), min(frame["x"] + frame["width"], size["width"])
    top, bottom = max(frame["y"], 0), min(frame["y"] + frame["height"], size["height"])
    return (left + right) / 2, (top + bottom) / 2


def _shot(ctx: Ctx, name: str) -> None:
    ctx.shots.mkdir(parents=True, exist_ok=True)
    ctx.page.screenshot(path=str(ctx.shots / name))


def check_28_shelf_card(ctx: Ctx) -> Result:
    """Полка → карточка (дефект 6): обложка плитки в карточке сразу, описание - словами.

    Плитки - три с обложкой за краем окна (:data:`_COLD_TILES`): их не грел никто, и
    карточка открывается холодной, как у владельца. Каждая - со свежей главной: человек
    долистывает до плитки и кликает, как только её картинка загрузилась. Обложка и имя
    обязаны встать за :data:`_AT_ONCE`, описание - текстом или словами «нет описания» за
    :data:`_COLD_CARD`, и обложка к этому мигу на месте.
    """
    _home(ctx)
    queries = ctx.page.evaluate(_COLD_TILES, _LIVE_TILE)
    if not queries:
        return Result(28, "Полка → обложка", False, None, "за краем окна нет плитки с обложкой")
    ok, said = True, []
    for number, query in enumerate(queries, 1):
        _home(ctx)
        index = ctx.page.evaluate(_TILE_BY_QUERY, [_LIVE_TILE, query])
        if index < 0:
            ok = False
            said.append(f"{query!r}: плитки на свежей главной нет")
            continue
        tile = ctx.page.locator(_LIVE_TILE).nth(index)
        tile.scroll_into_view_if_needed()
        loaded_by = time.monotonic() + 10.0
        while not tile.evaluate(_TILE_ART) and time.monotonic() < loaded_by:
            ctx.page.wait_for_timeout(50)
        ctx.page.evaluate(_ARM_CLICK)
        with _counting_gets(ctx) as gets:
            tile.click()
            at, look, clicked = _watch_card(ctx, _COLD_CARD)
        _shot(ctx, f"28-shelf-card-{number}.png")
        at_once = all((at[part] or _COLD_CARD) <= _AT_ONCE for part in ("poster", "title"))
        kept = bool(look.get("poster"))
        ok = ok and at_once and at["desc"] is not None and kept
        said.append(
            f"{query!r}: {_said_at(at)}; первый ответ через {gets.first_answer(clicked)} с, "
            f"GET {len(gets.asked)}; обложка в конце {'на месте' if kept else 'НЕТ'}; "
            f"описание {str(look.get('desc', ''))[:40]!r}"
        )
    return Result(28, "Полка → обложка", ok, None, " | ".join(said))


def check_29_card_tv_button(ctx: Ctx) -> Result:
    """Кнопка «на ТВ» (дефект 7): есть в карточке и сериала, и фильма, а не только при показе.

    Показа во вкладке прибор перед этим не запускает, так что кнопку не оправдывает идущий
    показ. С ``--play`` кнопка нажимается у фильма: картина обязана заиграть на приёмнике
    машины, позиция - вырасти между двумя замерами, затем показ останавливается.
    """
    label = ctx.english.get("web.detail.play_on_tv", "")
    if not label:
        return Result(29, "Кнопка на ТВ", False, None, "в каталоге нет web.detail.play_on_tv")
    seen: list[str] = []
    lost: list[str] = []
    for number, title in enumerate((_SERIES_TITLE, _MOVIE_TITLE)):
        why = _open_card_by_page(ctx, title)
        if why:
            lost.append(why)
            continue
        button = ctx.page.locator("[data-tc-card] button", has_text=label)
        with contextlib.suppress(Exception):
            button.first.wait_for(state="visible", timeout=_CARD_READY_WAIT)
        _shot(ctx, f"29-card-{number}.png")
        if button.count() and button.first.is_visible():
            seen.append(title)
        else:
            lost.append(f"{title!r}: кнопки {label!r} не видно (узлов {button.count()})")
    if lost:
        return Result(29, "Кнопка на ТВ", False, None, f"видна у {seen}; " + "; ".join(lost))
    if not ctx.allow_play:
        detail = f"видна у {seen}; каст не нажимался: --play не задан"
        return Result(29, "Кнопка на ТВ", True, None, detail)
    button = ctx.page.locator("[data-tc-card] button", has_text=label).first
    ok, said = _cast_from_card(ctx, button)
    return Result(29, "Кнопка на ТВ", ok, None, f"видна у {seen}; каст: {said}")


def _cast_from_card(ctx: Ctx, button: Any) -> tuple[bool, str]:
    """Нажать «на ТВ»: что пишет кнопка по ходу, заиграло ли, две позиции, затем стоп."""
    began = time.monotonic()
    button.click()
    words: list[str] = []
    state: dict[str, Any] = {}
    tv = ctx.page.locator("[data-tc-card-tv]")
    while time.monotonic() - began < _CAST_WAIT:
        text = (tv.first.text_content() or "").strip() if tv.count() else ""
        if text and not any(word.startswith(text + " (") for word in words):
            words.append(f"{text} ({time.monotonic() - began:.1f} с)")
        state = _state(ctx)
        if state.get("state") == "playing":
            break
        ctx.page.wait_for_timeout(1000)
    took = time.monotonic() - began
    first = _position(ctx)
    # Приёмник докладывает позицию рывками: пара через 5 с легла на плато при идущем
    # касте (стенд `.104`: пара 5.7 -> 5.7, а журнал остановил показ на 0:00:09).
    grew, _within = _await_position_growth(ctx, first)
    second = _position(ctx)
    text = (tv.first.text_content() or "").strip() if tv.count() else ""
    if text and not any(word.startswith(text + " (") for word in words):
        words.append(f"{text} ({time.monotonic() - began:.1f} с)")
    _shot(ctx, "29-cast.png")
    _post(ctx.base + "/api/control", {"cmd": "stop"})
    ctx.page.wait_for_timeout(3000)
    after = _state(ctx).get("state")
    playing = state.get("state") == "playing"
    said = (
        f"{'заиграло' if playing else 'НЕ заиграло'} за {took:.0f} с "
        f"({state.get('title')!r} на {state.get('tv')!r}), позиции {first} → {second}; "
        f"кнопка: {' → '.join(words) or 'без слов'}; после stop {after!r}"
    )
    return playing and grew, said


def _final_hits(base: str, query: str) -> list[dict[str, Any]]:
    """Выдача поиска, когда продукт снял с неё метку «ещё растёт» (или вышел срок)."""
    body = json.dumps({"query": query, "progressive": True}).encode("utf-8")
    deadline = time.monotonic() + _SEARCH_SETTLE
    while True:
        request = urllib.request.Request(
            base + "/api/search", data=body, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=30.0) as answer:
            # Итог поиск метит "0", а не снимает метку: иначе ждали бы чужого нового круга.
            partial = answer.headers.get("X-Torrcast-Partial") == "1"
            got = json.loads(answer.read())
        if not partial or time.monotonic() >= deadline:
            rows = got.get("results") if isinstance(got, dict) else None
            return [row for row in rows or [] if isinstance(row, dict)]
        time.sleep(1.0)


def _card_cover(base: str, key: str, query: str) -> bool | None:
    """Знает ли карточка картины её обложку: имя в ``poster`` и 200 на ``/api/poster``.

    Карточка не открылась вовсе (404, обрыв) - ``None``: это отказ карточки, пункта 22,
    а не приговор обложке, и падать из-за него весь пункт не должен.
    """
    url = f"{base}/api/card/{urllib.parse.quote(key)}?query={urllib.parse.quote(query)}&wait=1"
    deadline = time.monotonic() + _PARTIAL_WAIT
    while True:
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url), timeout=_CARD_GET_WAIT
            ) as answer:
                partial = answer.headers.get("X-Torrcast-Partial")
                card = json.loads(answer.read())
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return None
        if not partial or time.monotonic() >= deadline:
            break
        time.sleep(0.5)
    name = card.get("poster") if isinstance(card, dict) else None
    return bool(name) and _get(f"{base}/api/poster/{urllib.parse.quote(str(name))}")[0] == 200


def check_30_search_posters(ctx: Ctx) -> Result:
    """Обложки выдачи (дефект 8): у каждой картины, чья карточка знает обложку, она есть и
    на плитке выдачи - загруженной картинкой, по итогу поиска через интерфейс.

    Эталон - карточка той же картины (:func:`_card_cover`), а не поле выдачи: судить
    выдачу по ней самой значило бы мерить её согласие с собой.
    """
    placeholder = ctx.english.get("web.search.placeholder", "")
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    box = ctx.page.get_by_placeholder(placeholder, exact=True) if placeholder else None
    if box is None or box.count() == 0:
        return Result(30, "Обложки выдачи", False, None, f"поле поиска {placeholder!r} не найдено")
    box.first.fill(_MATRIX)
    box.first.press("Enter")
    hits = _final_hits(ctx.base, _MATRIX)
    selector = f'[data-tc-tile][data-tc-warm="{_MATRIX}"]'
    deadline = time.monotonic() + 20.0
    while time.monotonic() < deadline and ctx.page.locator(selector).count() < len(hits):
        ctx.page.wait_for_timeout(300)
    ctx.page.wait_for_timeout(3000)
    tiles = ctx.page.eval_on_selector_all(selector, _TILE_LOOKS)
    _shot(ctx, "30-search.png")
    covered: list[str] = []
    bare: list[str] = []
    refused: list[str] = []
    for hit in hits:
        name = str(hit.get("shown") or hit.get("title") or "")
        year = str(hit.get("year") or "")
        cover = _card_cover(ctx.base, str(hit.get("key") or ""), _MATRIX)
        if cover is None:
            refused.append(f"{name} {year}".strip())
        if not cover:
            continue
        covered.append(f"{name} {year}".strip())
        if not any(t["title"] == name and t["year"] == year and t["art"] for t in tiles):
            bare.append(f"{name} {year}".strip())
    with_art = sum(1 for tile in tiles if tile["art"])
    ok = bool(covered) and not bare
    detail = (
        f"«{_MATRIX}»: плиток с обложкой {with_art}/{len(tiles)}; находок {len(hits)}, "
        f"с обложкой в карточке {len(covered)}; без обложки на плитке: {bare or 'нет'}; "
        f"карточка не открылась: {refused or 'нет'}"
    )
    return Result(30, "Обложки выдачи", ok, None, detail)


def check_31_home_card(ctx: Ctx) -> Result:
    """Главная → карточка (дефект 13): видимая плитка, на которую смотрят, уже согрета.

    Курсор - на последней видимой плитке, :data:`_AIM_WAIT` секунд, клик. Обложка, имя и
    описание обязаны встать за :data:`_AT_ONCE`, а страница - спросить ``/api/card`` не
    больше :data:`_GETS_AT_MOST` раз за :data:`_GET_WINDOW` с.
    """
    tile = _home_tile(ctx)
    if tile is None:
        return Result(31, "Главная → карточка", False, None, "на главной нет видимой плитки")
    name = tile.locator(".tc-caption").text_content() or ""
    # Наводка - мышью в точку плитки, а не `hover()`: тот докручивает плитку в окно и
    # меняет сам экран, который греется. Клик - по самой плитке, где она теперь: ряд под
    # горящей плиткой растёт (`nav.js`), плитка уезжает из-под курсора, и клик в прежнюю
    # точку попадал в щель ряда или в поле у края полки. К этому мигу прогрев уже решён.
    aim = _middle(ctx, tile)
    ctx.page.mouse.move(*aim)
    ctx.page.wait_for_timeout(_AIM_WAIT * 1000)
    under = ctx.page.evaluate(_UNDER, list(aim))
    ctx.page.evaluate(_ARM_CLICK)
    with _counting_gets(ctx) as gets:
        try:
            tile.click(timeout=5000)
        except Exception as error:  # промах клика - строка пункта, а не падение прибора
            under = f"{under}; клик не прошёл: {type(error).__name__}"
        at, _look, clicked = _watch_card(ctx, _GET_WINDOW)
        _shot(ctx, "31-home-card.png")
        rest = _GET_WINDOW - (time.monotonic() - gets.began)
        if rest > 0:
            ctx.page.wait_for_timeout(rest * 1000)
    at_once = all((spent or _GET_WINDOW) <= _AT_ONCE for spent in at.values())
    ok = at_once and len(gets.asked) <= _GETS_AT_MOST
    detail = (
        f"{name.strip()!r} после {_AIM_WAIT:.0f} с под курсором (в миг клика под ним "
        f"{under!r}): {_said_at(at)}; "
        f"первый ответ /api/card через {gets.first_answer(clicked)} с; "
        f"GET /api/card за {_GET_WINDOW:.0f} с: {len(gets.asked)} (потолок {_GETS_AT_MOST})"
    )
    return Result(31, "Главная → карточка", ok, None, detail)


#: Серия и секунда, на которых пункты 33 и 36 сами ставят место сериала. Вторая серия, а
#: не первая: место на s1e1 не отличить от «сериал начали с начала», и пункт зеленел бы
#: на том самом дефекте, который сторожит.
_PLACE_EPISODE: Final = "s1e2"
_PLACE_AT: Final = 300.0
#: Допуск «с того же места», секунды: показ садится на опорный кадр не позже закладки
#: (:func:`torrcast.usecases.feed_pack.feed_restart._begin`), сторож пишет место раз в 10 с.
_PLACE_SLACK: Final = 30.0
#: Запрос, которому заведомо нечего найти: отказ без юнита и без упаковки (пункт 34).
_REFUSED_QUERY: Final = "зщхъэжд нет такой картины 1234"
#: Кнопки, видимые человеку, и накрыто ли каждую чем-то сверху: накрытая кнопка видна,
#: а нажатие уходит в то, что лежит поверх, - то есть не делает ничего (пункт 34).
_BUTTONS_JS: Final = """() => [...document.querySelectorAll('button, [role=button], a[href]')]
  .filter((b) => b.offsetParent !== null && getComputedStyle(b).visibility !== 'hidden')
  .map((b) => { const r = b.getBoundingClientRect();
    const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    return {text: (b.innerText || b.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim(),
            open: hit === b || b.contains(hit)}; })"""
#: Что пункт 34 рвёт, чтобы вкладка потеряла поток: плейлисты, сегменты, заголовок.
_STREAM_ROUTES: Final = ("**/*.m3u8", "**/*.m4s", "**/*.ts", "**/init*.mp4")


def _card_key(ctx: Ctx) -> str:
    """Ключ картины открытой карточки - из её адреса ``/card/<ключ>``."""
    tail = ctx.page.url.split("/card/", 1)[-1].split("?", 1)[0]
    return urllib.parse.unquote(tail)


def _place_of(ctx: Ctx, key: str) -> tuple[str | None, float | None]:
    """Место картины из ``GET /api/history``: подпись серии и секунда; записи нет - ``None``."""
    code, body = _get(ctx.base + "/api/history")
    if code != 200:
        return None, None
    with contextlib.suppress(json.JSONDecodeError, AttributeError):
        for item in json.loads(body).get("items", []):
            if isinstance(item, dict) and item.get("key") == key:
                pos = item.get("pos")
                return item.get("label"), float(pos) if isinstance(pos, int | float) else None
    return None, None


def _stop_show(ctx: Ctx) -> None:
    """Погасить свой показ и дождаться, пока экземпляр это подтвердит (до 20 с)."""
    _post(ctx.base + "/api/control", {"cmd": "stop"})
    began = time.monotonic()
    while time.monotonic() - began < 20.0:
        if _state(ctx).get("state") not in ("playing", "starting", "paused", "buffering"):
            return
        time.sleep(0.5)


def _video_times(ctx: Ctx, count: int = 3, gap: float = 2.0) -> list[float]:
    """Несколько замеров ``currentTime`` подряд - «растёт» судится по ним, а не по одному."""
    times: list[float] = []
    for index in range(count):
        if index:
            ctx.page.wait_for_timeout(int(gap * 1000))
        at = _video(ctx, "v => v.currentTime")
        times.append(float(at) if isinstance(at, int | float) else -1.0)
    return times


def _growing(times: list[float]) -> bool:
    return len(times) > 1 and all(later > earlier for earlier, later in itertools.pairwise(times))


def _overlay_text(ctx: Ctx) -> str:
    return str(
        ctx.page.evaluate(
            "() => [...document.querySelectorAll('.tc-refused, .tc-lost, .tc-preparing')]"
            ".map((n) => n.innerText.replace(/\\s+/g, ' ').trim()).join(' | ')"
        )
    )


def check_32_film_frame(ctx: Ctx) -> Result:
    """Фильм до кадра во вкладке: «Играть» у «Матрицы» → кадр и два растущих замера подряд.

    ⚠️ На живом рое пункт зелёный и на 9a6f7307 (там кадр был за 13,6 с): прод не дошёл до
    кадра из-за записанной раздачи без пиров (60 с приговора, ``_dead_release``) и роя
    медленнее потока (0,19x), а мёртвый рой прибор заказать не может. Пункт - сторож
    результата, а не отрицательная проба; граница названа в карточке.
    """
    guard = _playback_guard(32, "Кадр", ctx, True, "")
    if guard:
        return guard
    refusal = _open_card_by_page(ctx, _LATIN_KNOWN_TITLE)
    if refusal is not None:
        return Result(32, "Кадр", False, None, refusal)
    began = time.monotonic()
    ctx.page.locator("[data-tc-play]").first.click()
    if not _await_playback(ctx):
        screen = _overlay_text(ctx)
        _stop_show(ctx)
        why = f"кадра нет за {_PLAY_START_WAIT / 1000:.0f} с; на экране: {screen!r}"
        return Result(32, "Кадр", False, None, why)
    took = time.monotonic() - began
    times = _video_times(ctx)
    _stop_show(ctx)
    shown = " -> ".join(f"{t:.1f}" for t in times)
    return Result(32, "Кадр", _growing(times), None, f"кадр за {took:.1f} с, ход {shown}")


def _plant_place(ctx: Ctx) -> tuple[str | None, float | None, str]:
    """Поставить место сериала ТАК ЖЕ, как человек: серия s1e2, перемотка, стоп.

    Возвращает ключ картины и секунду легшего места, либо причину, почему место не легло.
    """
    refusal = _open_card_by_page(ctx, _SERIES_TITLE)
    if refusal is not None:
        return None, None, refusal
    key = _card_key(ctx)
    target = ctx.page.locator(f'[data-tc-episode="{_PLACE_EPISODE}"]')
    with contextlib.suppress(Exception):
        target.first.wait_for(state="visible", timeout=30000)
    if target.count() == 0:
        return None, None, f"серии {_PLACE_EPISODE} нет в карточке {_SERIES_TITLE!r}"
    target.first.click()
    pair, why = _await_shown(ctx)
    if pair != _PLACE_EPISODE:
        _stop_show(ctx)
        return None, None, why or f"играет {pair!r}, а не {_PLACE_EPISODE}"
    ctx.page.eval_on_selector("video", f"v => {{ v.currentTime = {_PLACE_AT}; }}")
    label, pos = None, None
    began = time.monotonic()
    while time.monotonic() - began < 2 * _PLAY_START_WAIT / 1000.0:
        label, pos = _place_of(ctx, key)
        if label == _PLACE_EPISODE and pos is not None and abs(pos - _PLACE_AT) <= _PLACE_SLACK:
            break
        time.sleep(1.0)
    _stop_show(ctx)
    label, pos = _place_of(ctx, key)
    if label != _PLACE_EPISODE or pos is None or abs(pos - _PLACE_AT) > _PLACE_SLACK:
        return None, None, f"место не легло: {label!r} на {pos!r}"
    return key, pos, ""


#: Сколько ждать, пока продукт САМ назовёт показ идущим: его бюджет подъёма
#: (:data:`torrcast.domain.start_settings.START_BUDGET`, 350 с) и запас. Перебор раздач
#: на стенде идёт минутами (живой прогон 11-09: восемь раздач s1e2 до упаковки).
_SHOW_UP_WAIT: Final = 360.0


def _await_shown(ctx: Ctx) -> tuple[str | None, str]:
    """Дождаться показа, который продукт сам зовёт идущим; вернуть его серию (``s1e2``).

    ``readyState >= 3`` вкладки тут мало: первые секунды упаковки дают кадр и тогда, когда
    рой отдаёт 0,00x и подъём ещё ждёт картинку (живой прогон 11-09: место, поставленное
    на таком кадре, откатилось вместе с не поднявшимся показом, и это верно). Годен показ,
    у которого ``/api/state`` - ``playing`` и ``currentTime`` вкладки идёт. У фильма серии
    нет - вернётся пустая строка.
    """
    began = time.monotonic()
    state: dict[str, Any] = {}
    while time.monotonic() - began < _SHOW_UP_WAIT:
        state = _state(ctx)
        if state.get("state") == "playing" and _growing(_video_times(ctx, 2, 1.0)):
            season, episode = state.get("season"), state.get("episode")
            return (
                f"s{season}e{episode}" if season is not None and episode is not None else ""
            ), ""
        ctx.page.wait_for_timeout(2000)
    why = state.get("refusal") or state.get("last_error") or f"state={state.get('state')!r}"
    return None, f"продукт не назвал показ идущим за {time.monotonic() - began:.0f} с: {why}"


def check_33_series_place(ctx: Ctx) -> Result:
    """Сериал с места: «Играть» у начатого сериала продолжает серию и секунду закладки.

    Место прибор ставит сам (:func:`_plant_place`), и серия вторая: на 9a6f7307 «Играть»
    уходило дверью меню (``--pick``) обычным путём, играло s1e1 с нуля и стирало место.
    """
    guard = _playback_guard(33, "Сериал с места", ctx, True, "")
    if guard:
        return guard
    key, planted, why = _plant_place(ctx)
    if key is None or planted is None:
        blocked = f"стенд не дал показа {_PLACE_EPISODE}: {why}"
        return Result(33, "Сериал с места", False, blocked, "место не поставлено")
    refusal = _open_card_by_page(ctx, _SERIES_TITLE)
    if refusal is not None:
        return Result(33, "Сериал с места", False, None, refusal)
    began = time.monotonic()
    ctx.page.locator("[data-tc-play]").first.click()
    pair, why = _await_shown(ctx)
    if pair is None:
        screen = _overlay_text(ctx)
        _stop_show(ctx)
        label, pos = _place_of(ctx, key)
        why = f"{why}; на экране {screen!r}; место теперь {label!r} на {pos!r}"
        return Result(33, "Сериал с места", False, None, why)
    took = time.monotonic() - began
    times = _video_times(ctx)
    _stop_show(ctx)
    ok = pair == _PLACE_EPISODE and abs(times[0] - planted) <= _PLACE_SLACK and _growing(times)
    shown = " -> ".join(f"{t:.1f}" for t in times)
    detail = (
        f"место {_PLACE_EPISODE} на {planted:.1f} с; «Играть» за {took:.1f} с -> {pair}, "
        f"ход {shown}"
    )
    return Result(33, "Сериал с места", ok, None, detail)


def _halt_screen(ctx: Ctx, screen: str, allowed: tuple[str, ...]) -> tuple[bool, str]:
    """Экран без плёнки: что на нём видно, что из этого не нажимается, и выводит ли «Назад».

    Годен экран, где каждая видимая кнопка открыта и названа в ``allowed``, «Назад» среди
    них есть и уводит с ``/play``. Накрытая кнопка - мёртвая: её видно, а нажатие уходит в
    экран поверх неё (на 9a6f7307 так лежала вся панель плеера, шесть кнопок).
    """
    _wake_panel(ctx)
    buttons = ctx.page.evaluate(_BUTTONS_JS)
    title = ctx.page.inner_text(screen).replace("\n", " ").strip()
    dead = [b["text"] for b in buttons if not b["open"]]
    known = {word.casefold() for word in allowed}
    strange = [b["text"] for b in buttons if b["open"] and b["text"].casefold() not in known]
    back = ctx.english.get("web.player.back", "")
    exit_button = ctx.page.locator(f"{screen} button", has_text=back) if back else None
    where = "«Назад» нет"
    if exit_button is not None and exit_button.count() > 0:
        exit_button.first.click()
        ctx.page.wait_for_timeout(3000)
        path = ctx.page.evaluate("location.pathname")
        where = f"«Назад» -> {path}"
    left = where.startswith("«Назад» -> ") and not where.endswith("/play")
    ok = left and not dead and not strange
    shown = [b["text"] for b in buttons if b["open"]]
    detail = f"«{title[:80]}»; открытые {shown}, мёртвые {dead}, лишние {strange}, {where}"
    return ok, detail


def check_34_halt_exit(ctx: Ctx) -> Result:
    """Выход с экрана без плёнки: у отказа и у потери потока рабочий «Назад», мёртвых кнопок нет.

    Отказ зовётся тем же запросом, что шлёт «Играть» карточки (``TCApi.play`` с ``here``),
    по картине, которой нет: юнит не поднимается, но идущий показ ЭТОГО экземпляра заказ
    снимет, поэтому только по ``--play``. Потеря - настоящий показ, у которого прибор рвёт
    поток в самой вкладке. Надпись отказа печатается, но не судится: причину «ничего не
    нашлось» каталог вкладки не называет, и новая строка - решение владельца.
    """
    guard = _playback_guard(34, "Выход", ctx, True, "")
    if guard:
        return guard
    back = ctx.english.get("web.player.back", "")
    retry = ctx.english.get("web.player.retry", "")
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_function("() => window.TCApi && TCApi.play", timeout=15000)
    ctx.page.evaluate("(q) => TCApi.play({query: q, here: true})", _REFUSED_QUERY)
    ctx.page.wait_for_selector(".tc-refused", timeout=_PLAY_START_WAIT)
    refused_ok, refused = _halt_screen(ctx, ".tc-refused", (back,))
    refusal = _open_card_by_page(ctx, _MOVIE_TITLE)
    if refusal is not None:
        return Result(34, "Выход", False, None, f"отказ: {refused}; потеря: {refusal}")
    ctx.page.locator("[data-tc-play]").first.click()
    if not _await_playback(ctx):
        _stop_show(ctx)
        return Result(34, "Выход", False, None, f"отказ: {refused}; потеря: кадра не было")
    for pattern in _STREAM_ROUTES:
        ctx.page.route(pattern, lambda route: route.abort())
    try:
        ctx.page.wait_for_selector(".tc-lost", timeout=_PLAY_START_WAIT)
    finally:
        for pattern in _STREAM_ROUTES:
            ctx.page.unroute(pattern)
    lost_ok, lost = _halt_screen(ctx, ".tc-lost", (back, retry))
    _stop_show(ctx)
    return Result(34, "Выход", refused_ok and lost_ok, None, f"отказ: {refused}; потеря: {lost}")


def check_35_same_on_tv(ctx: Ctx) -> Result:
    """Одна картина и во вкладке, и на ТВ: фильм из карточки идёт во вкладке, потом «На ТВ».

    Приёмник судит пункт 9 (тот же url у обоих концов, ход позиции на ТВ, громкость), но с
    чистого показа из карточки, а не хвостом цепочки 4-10. ⚠️ Зелёный и на 9a6f7307: одна
    и та же упаковка отдаётся обоим концам, и прод это подтверждал (бот на ТВ играл).
    Разница в проде была не в концах, а в том, что показ вкладки снимался чужим подъёмом с
    тем же именем юнита; её сторожит не этот пункт, а замер чередования в карточке.
    """
    guard = _playback_guard(35, "Та же картина на ТВ", ctx, True, "")
    if guard:
        return guard
    refusal = _open_card_by_page(ctx, _MOVIE_TITLE)
    if refusal is not None:
        return Result(35, "Та же картина на ТВ", False, None, refusal)
    ctx.page.locator("[data-tc-play]").first.click()
    if not _await_playback(ctx):
        screen = _overlay_text(ctx)
        _stop_show(ctx)
        return Result(35, "Та же картина на ТВ", False, None, f"во вкладке кадра нет: {screen!r}")
    tab = _video_times(ctx, 2)
    tv = check_9_on_tv(ctx, True)
    _stop_show(ctx)
    shown = " -> ".join(f"{t:.1f}" for t in tab)
    ok = _growing(tab) and tv.ok
    return Result(35, "Та же картина на ТВ", ok, None, f"вкладка {shown}; ТВ: {tv.detail}")


def check_36_place_survives(ctx: Ctx) -> Result:
    """Место цело: отменённый подъём другой серии из веба не трогает сохранённое место.

    Стартовая запись показа ложится под ключ картины ДО юнита, и на 9a6f7307 переживала
    любой исход: подъём s1e1, снятый остановкой, оставлял место s1e1 с нуля, и дальше
    бот играл с него. Остановка идёт в тот миг, когда стартовая запись уже легла, - раньше
    менять было бы нечего, позже показ успел бы подняться и место стало бы честным.
    """
    guard = _playback_guard(36, "Место цело", ctx, True, "")
    if guard:
        return guard
    refusal = _open_card_by_page(ctx, _SERIES_TITLE)
    if refusal is not None:
        return Result(36, "Место цело", False, None, refusal)
    key = _card_key(ctx)
    label, pos = _place_of(ctx, key)
    if label != _PLACE_EPISODE or pos is None:
        planted_key, _, why = _plant_place(ctx)
        if planted_key is None:
            blocked = f"стенд не дал показа {_PLACE_EPISODE}: {why}"
            return Result(36, "Место цело", False, blocked, "место не поставлено")
        refusal = _open_card_by_page(ctx, _SERIES_TITLE)
        if refusal is not None:
            return Result(36, "Место цело", False, None, refusal)
        label, pos = _place_of(ctx, key)
    other = ctx.page.locator('[data-tc-episode="s1e1"]')
    with contextlib.suppress(Exception):
        other.first.wait_for(state="visible", timeout=30000)
    if other.count() == 0 or pos is None:
        return Result(36, "Место цело", False, None, f"нет s1e1 или места ({label!r}, {pos!r})")
    other.first.click()
    began = time.monotonic()
    written = None
    while time.monotonic() - began < _SHOW_UP_WAIT:
        now = _place_of(ctx, key)
        if now != (label, pos):
            written = now
            break
        time.sleep(0.2)
    if written is None:
        _stop_show(ctx)
        why = f"стартовая запись s1e1 не легла за {_PLAY_START_WAIT / 1000:.0f} с"
        return Result(36, "Место цело", False, None, why)
    at_stop = _state(ctx).get("state")
    _stop_show(ctx)
    time.sleep(2.0)
    after_label, after_pos = _place_of(ctx, key)
    ok = after_label == label and after_pos is not None and abs(after_pos - pos) <= 3.0
    detail = (
        f"место {label} на {pos:.1f}; s1e1 -> стартовая запись {written[0]} на {written[1]!r} "
        f"через {time.monotonic() - began:.1f} с, стоп при state={at_stop!r}; "
        f"место после: {after_label!r} на {after_pos!r}"
    )
    return Result(36, "Место цело", ok, None, detail)


#: Щуп бота без Telegram (:mod:`botstop_probe`): лежит рядом с приёмкой, а меряет дерево,
#: которое ему назвали, - так пункт краснеет на старом коммите, где щупа ещё не было.
_BOT_STOP_PROBE: Final = Path(__file__).resolve().parent / "botstop_probe.py"


#: Полоса вкладки в пункте 38, байт/с: медленный рой. Первый кусок едет секунды, и экран
#: до первого кадра стоит дольше шага замера, а не мелькает между снимками.
_SLOW_BYTES_S: Final = 150_000
#: Снимок экрана до первого кадра: какой экран, какие кнопки видны, был ли уже кадр.
_BEFORE_FRAME_JS: Final = """() => {
  const v = document.querySelector('video');
  const screen = ['preparing', 'buffering-screen', 'refused', 'lost']
    .find((n) => document.querySelector('.tc-' + n)) || '';
  const buttons = [...document.querySelectorAll('button, [role=button]')]
    .filter((b) => b.offsetParent !== null && getComputedStyle(b).visibility !== 'hidden')
    .map((b) => (b.innerText || b.getAttribute('aria-label') || '').replace(/\\s+/g, ' ').trim());
  return {framed: !!v && v.readyState >= 3 && !v.paused && !screen, screen, buttons};
}"""


def _narrow(ctx: Ctx, bytes_s: int) -> Any:
    """Сузить полосу вкладки (CDP) до ``bytes_s``; ``-1`` снимает сужение."""
    cdp = ctx.page.context.new_cdp_session(ctx.page)
    cdp.send("Network.enable")
    conditions = {"offline": False, "latency": 0, "uploadThroughput": -1}
    cdp.send("Network.emulateNetworkConditions", {**conditions, "downloadThroughput": bytes_s})
    return cdp


def check_38_bare_until_frame(ctx: Ctx) -> Result:
    """До первого кадра видно только то, что работает: «Назад», без панели показа.

    Прод 11-09: «вижу буферинг и куча кнопок, которые не работают». Холодный пуск фильма
    «Играть» карточки при полосе медленного роя; до кадра прибор каждые 0,3 с будит панель
    мышью, как зритель, и снимает видимые кнопки. Годен пуск, где экран буферизации в
    снимках был, «Назад» на нём есть, а кроме «Назад» нет ни одной кнопки. На 9a6f7307
    буферизация лежала поверх панели: «−10 S», «+10 S», «PLAY ON TV», «⤢», «✕».
    """
    guard = _playback_guard(38, "До кадра", ctx, True, "")
    if guard:
        return guard
    back = ctx.english.get("web.player.back", "")
    refusal = _open_card_by_page(ctx, _LATIN_KNOWN_TITLE)
    if refusal is not None:
        return Result(38, "До кадра", False, None, refusal)
    seen: dict[str, set[str]] = {}
    frame_at: float | None = None
    cdp = _narrow(ctx, _SLOW_BYTES_S)
    began = time.monotonic()
    try:
        ctx.page.locator("[data-tc-play]").first.click()
        while time.monotonic() - began < _PLAY_START_WAIT / 1000.0:
            ctx.page.mouse.move(200 + len(seen) * 3 + (int(time.monotonic() * 10) % 7), 300)
            snap = ctx.page.evaluate(_BEFORE_FRAME_JS)
            if snap["framed"]:
                frame_at = time.monotonic() - began
                break
            if snap["screen"]:
                seen.setdefault(snap["screen"], set()).update(t for t in snap["buttons"] if t)
            ctx.page.wait_for_timeout(300)
    finally:
        cdp.send(
            "Network.emulateNetworkConditions",
            {"offline": False, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1},
        )
        cdp.detach()
    _stop_show(ctx)
    extra = {screen: sorted(b for b in found if b != back) for screen, found in seen.items()}
    shown = {screen: sorted(found) for screen, found in seen.items()}
    waited = "кадра не было" if frame_at is None else f"кадр за {frame_at:.1f} с"
    buffering = seen.get("buffering-screen")
    ok = frame_at is not None and buffering is not None and back in buffering
    ok = ok and not any(extra.values())
    return Result(38, "До кадра", ok, None, f"{waited}; до кадра видно {shown}; лишние {extra}")


#: Сколько секунд после «Назад» экземпляр вправе ещё поднимать брошенный показ.
_CALL_OFF_WAIT: Final = 10.0
#: Сколько после этого смотреть, что брошенный показ не поднялся позже.
_CALL_OFF_WATCH: Final = 30.0


def check_39_back_calls_off(ctx: Ctx) -> Result:
    """«Назад» с экрана подготовки снимает подъём: экземпляр в покое за считанные секунды.

    Заказ - тем же ``TCApi.play`` с ``here``, что шлёт «Играть» карточки; «Назад» жмётся
    через 3 с подготовки, пока продукт ищет раздачу. Годен уход, после которого
    ``/api/state`` стал ``idle`` за ``_CALL_OFF_WAIT`` с и не ожил до конца наблюдения.
    На 9a6f7307 после «Назад» экземпляр 60 с держал ``starting``, а ящик получил картину:
    показ поднимался для никого и тянул рой, а следующее «Играть» с ним сталкивалось.
    """
    guard = _playback_guard(39, "Назад с подготовки", ctx, True, "")
    if guard:
        return guard
    back = ctx.english.get("web.player.back", "")
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_function("() => window.TCApi && TCApi.play", timeout=15000)
    ctx.page.evaluate("(q) => TCApi.play({query: q, here: true})", _LATIN_KNOWN_TITLE)
    ctx.page.wait_for_selector(".tc-preparing", timeout=20000)
    ctx.page.wait_for_timeout(3000)
    screen = _overlay_text(ctx)
    button = ctx.page.locator(".tc-preparing button", has_text=back)
    if not back or button.count() == 0:
        _stop_show(ctx)
        return Result(39, "Назад с подготовки", False, None, f"«Назад» нет; на экране {screen!r}")
    button.first.click()
    pressed = time.monotonic()
    idle_at: float | None = None
    woke: list[str] = []
    while time.monotonic() - pressed < _CALL_OFF_WAIT + _CALL_OFF_WATCH:
        word = str(_state(ctx).get("state"))
        if word == "idle" and idle_at is None:
            idle_at = time.monotonic() - pressed
        elif word != "idle" and idle_at is not None:
            woke.append(f"{word} на {time.monotonic() - pressed:.0f} с")
        time.sleep(0.5)
    path = ctx.page.evaluate("location.pathname")
    _stop_show(ctx)
    ok = idle_at is not None and idle_at <= _CALL_OFF_WAIT and not woke and path != "/play"
    said = "покоя не было" if idle_at is None else f"покой через {idle_at:.1f} с"
    detail = f"«{screen[:60]}» -> {path}; {said}; ожил: {woke or 'нет'}"
    return Result(39, "Назад с подготовки", ok, None, detail)


def check_37_bot_stop(repo: Path) -> Result:
    """``cast stop`` в боте проходит, пока исполнитель занят чужим долгим подъёмом.

    Мерится там, где лежит дерево (``--repo``), теми же вызовами, что делает бот на
    сообщение из чата (:meth:`tgbot.bot.Bot.dispatch`), но без сети Telegram. На 9a6f7307
    остановка вставала в ту же очередь, что и показ, и получала «Предыдущий запрос cast
    ещё выполняется», а подъём шёл дальше.
    """
    python = repo / ".venv" / "bin" / "python"
    if not python.exists():
        return Result(37, "Стоп в боте", False, f"нет {python}", "боту негде подняться")
    proc = subprocess.run(
        [str(python), str(_BOT_STOP_PROBE), str(repo)],
        cwd=str(repo),
        capture_output=True,
        text=True,
        stdin=subprocess.DEVNULL,
        timeout=90,
    )
    lines = proc.stdout.strip().splitlines()
    try:
        said = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError):
        tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-8:])
        return Result(37, "Стоп в боте", False, None, f"rc={proc.returncode}: {tail}")
    ended = said.get("ended")
    ok = not said.get("busy") and bool(said.get("stop")) and isinstance(ended, float) and ended < 5
    detail = (
        f"«cast stop» посреди подъёма: «занято» {'было' if said.get('busy') else 'не было'}, "
        f"остановка {'позвана' if said.get('stop') else 'не позвана'}, подъём "
        f"{f'кончился через {ended} с' if ended is not None else 'шёл дальше 20 с'}; "
        f"дерево {said.get('tree')}"
    )
    return Result(37, "Стоп в боте", ok, None, detail)


def _print(results: list[Result]) -> int:
    for result in sorted(results, key=lambda r: r.number):
        state = "OK" if result.ok else ("BLOCKED" if result.blocked else "FAIL")
        print(f"[{result.number:>2}] {result.name:<10} {state:<8} {result.detail}")
        if result.blocked:
            print(f"      заблокирован: {result.blocked}")
    passed = sum(1 for r in results if r.ok)
    print(f"\nитог: {passed} из {len(results)} пунктов зелёные")
    return 0 if passed == len(results) else 1


def _guarded(number: int, name: str, run: Callable[[], Result]) -> Result:
    """Упавший пункт - провал ЭТОГО пункта, а не потеря всей приёмки.

    Живой прогон дошёл до одного из поздних пунктов и умер на `<video>`, которого не
    было в DOM: остальные приговоры пропали бы вместе с ним, включая уже снятые.
    Приёмка обязана назвать их все - иначе она не приёмка, а первый отказ.
    """
    try:
        return run()
    except Exception as error:  # скрипту не дано права уронить прогон целиком
        return Result(number, name, False, None, f"скрипт упал: {type(error).__name__}: {error}")


def _video(ctx: Ctx, expr: str) -> Any:
    """Спросить `<video>`, если он есть; нет его - `None`, а не падение скрипта."""
    if ctx.page.locator("video").count() == 0:
        return None
    return ctx.page.eval_on_selector("video", expr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base", default="http://localhost:8479", help="адрес запущенного экземпляра torrcast"
    )
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument(
        "--play",
        action="store_true",
        help="разрешить настоящий показ (пп. 4,6-11,20,32-36) - отнимает полосу упаковки у соседа",
    )
    parser.add_argument("--shots", type=Path, default=Path("/tmp/web-acceptance-shots"))
    parser.add_argument(
        "--only",
        default="",
        help="номера пунктов через запятую; пункт без своего предшественника заблокирован",
    )
    args = parser.parse_args()
    only = {int(number) for number in args.only.split(",") if number.strip()}

    en_code, en_body = _get(args.base + "/api/phrases")
    english = json.loads(en_body) if en_code == 200 else {}

    results: list[Result] = []

    def pick(number: int, name: str, run: Callable[[], Result]) -> bool:
        """Прогнать пункт, если он выбран; ответ - зелёный ли он (для зависимых)."""
        if only and number not in only:
            return False
        result = _guarded(number, name, run)
        results.append(result)
        return result.ok

    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        # Chromium без окна по умолчанию прячет полосы прокрутки (`--hide-scrollbars`):
        # с этим флагом ширина любой полосы 0, и пункт 26 зеленел бы на любой вёрстке.
        browser = driver.chromium.launch(headless=True, ignore_default_args=["--hide-scrollbars"])
        # 31 и 28 - первыми, на свежей странице: пункты ниже водят по полкам и греют
        # плитки, и холодную карточку после них было бы не с чего открыть. Окно - экран
        # ПК владельца (1920x1080), на котором сняты его дефекты карточки.
        wide = Ctx(
            args.base,
            browser.new_page(viewport={"width": 1920, "height": 1080}),
            args.play,
            args.shots,
            english,
        )
        pick(31, "Главная → карточка", lambda: check_31_home_card(wide))
        pick(28, "Полка → обложка", lambda: check_28_shelf_card(wide))
        pick(30, "Обложки выдачи", lambda: check_30_search_posters(wide))
        pick(29, "Кнопка на ТВ", lambda: check_29_card_tv_button(wide))
        page = browser.new_page()
        ctx = Ctx(args.base, page, args.play, args.shots, english)
        pick(1, "Главная", lambda: check_1_home(ctx))
        pick(17, "Вбок", lambda: check_17_wheel(ctx))
        pick(18, "Подпись", lambda: check_18_caption_scroll(ctx))
        pick(19, "Латиница", lambda: check_19_latin_titles(ctx))
        pick(21, "Слияние", lambda: check_21_merge_hits(ctx))
        pick(23, "Наведение", lambda: check_23_hover(ctx))
        pick(24, "Стрелки", lambda: check_24_arrows(ctx))
        pick(25, "Колесо", lambda: check_25_page_wheel(ctx))
        pick(26, "Полосы", lambda: check_26_bars(ctx))
        pick(27, "Под мышью", lambda: check_27_under_pointer(ctx))
        ok2 = pick(2, "Поиск", lambda: check_2_search(ctx))
        ok3 = pick(3, "Карточка", lambda: check_3_card(ctx, ok2))
        ok4 = pick(4, "Показ", lambda: check_4_playback(ctx, ok3))
        ok5 = pick(5, "Закладка", lambda: check_5_bookmark(ctx, ok4))
        pick(6, "Сначала", lambda: check_6_restart(ctx, ok5))
        ok7 = pick(7, "Сериал", lambda: check_7_series(ctx, ok3))
        pick(8, "Автопереход", lambda: check_8_autoplay(ctx, ok7))
        ok9 = pick(9, "На ТВ", lambda: check_9_on_tv(ctx, ok4 or ok7))
        ok10 = pick(10, "На комп", lambda: check_10_on_pc(ctx, ok9))
        pick(20, "Уход", lambda: check_20_leave_tears_down(ctx, ok10))
        pick(11, "Стрелки", lambda: check_11_arrows(ctx))
        # Пункты 32-36 - по одному показу на пункт, каждый гасит свой показ сам.
        pick(32, "Кадр", lambda: check_32_film_frame(ctx))
        pick(33, "Сериал с места", lambda: check_33_series_place(ctx))
        pick(34, "Выход", lambda: check_34_halt_exit(ctx))
        pick(35, "Та же картина на ТВ", lambda: check_35_same_on_tv(ctx))
        pick(36, "Место цело", lambda: check_36_place_survives(ctx))
        pick(38, "До кадра", lambda: check_38_bare_until_frame(ctx))
        pick(39, "Назад с подготовки", lambda: check_39_back_calls_off(ctx))
        browser.close()

    pick(15, "Обложки", lambda: check_15_posters(args.base))
    pick(16, "Мусор", lambda: check_16_junk(args.base))
    pick(22, "Полка → карточка", lambda: check_22_shelf_cards_open(args.base))
    pick(12, "Франшиза", lambda: check_12_franchise(args.base))
    pick(13, "Тексты", lambda: check_13_texts(args.base))
    pick(14, "Гейт", lambda: check_14_gate(args.repo))
    pick(37, "Стоп в боте", lambda: check_37_bot_stop(args.repo))
    return _print(results)


if __name__ == "__main__":
    raise SystemExit(main())
