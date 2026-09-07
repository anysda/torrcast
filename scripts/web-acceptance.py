#!/usr/bin/env python3
"""Прибор приёмки TC-1116 (ТЗ §11): 16 пунктов, каждый - число, а не «открылось».

Инструмент разработчика: headless Chromium (playwright), в устанавливаемый пакет не
входит и в зависимости продукта не входит - как ``scripts/kinshelfprobe.py`` и
``scripts/recodebench.py``. Ставится только на стенде (в этой волне - CT502,
``/opt/pwenv``), звать оттуда против живого стенда::

    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers /opt/pwenv/bin/python3 \
        scripts/web-acceptance.py --base http://192.168.1.104:8479

Пункты 12-13 и 15-16 не ходят через браузер вовсе, им хватает выдачи; пункт 14 обязан
запускаться там, где лежит дерево ``torrcast`` (``--repo``), а не с CT502 - там его нет.

Прибор обязан называть, ЧЕМ именно он недоволен - конкретный запрос, конкретное число,
конкретный отсутствующий узел DOM. Ни один пункт не пропускается молча: у каждого либо
оценка, либо явная пометка «заблокирован» с причиной.

🔴 Полоса упаковки на стенде ОДНА (``/root/hlsprobe/`` замер 06-09-2026): второй читатель
уводит головку у первого. Показ (пункты 4, 6, 8-10) поэтому НЕ запускается сам по себе -
только по ``--play``, и без него прибор доказывает выключение отчётом ``/api/state``, а
не имитацией. Пункты 9-10 (Chromecast) читают состояние приёмника через продуктовое
``/api/state``, а не вторым ``pychromecast``: второй сендер к тому же приёмнику неотличим
от первого для приёмника и рвёт чужой показ
(:class:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver`,
докстрока класса) - наблюдать чужой каст безопасно чем угодно, кроме этого.

Контракт DOM (``data-tc-*``) согласован оркестратором и вывешен полосам волны: страница
вешает ``data-tc-tile``, ``data-tc-card``, ``data-tc-card-description``,
``data-tc-card-rating``, ``data-tc-play`` и ``data-tc-episode``, плеер -
``data-tc-audio-option`` и ``data-tc-next-episode``. Заголовки полок и кнопки прибор ищет
по ТЕКСТУ из ``/api/phrases`` - это переживёт смену разметки, а не переживёт смену каталога.

⚠️ Пункт 13 - грепом, а не разбором AST: однословный литерал (``'Play'``) от ключа
каталога не отличить простым грепом по кавычкам. Это названный предел точности
инструмента, а не дыра, которую прячут.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

#: Три полки главной (ТЗ §11 п.1) - ключи каталога `torrcast/domain/catalogs/web/en.py`.
_SHELF_KEYS: Final = (
    "web.shelf.continue_watching",
    "web.shelf.new",
    "web.shelf.popular",
)

#: Те же десять франшиз, что и в `scripts/kinshelfprobe.py` (ТЗ §8) - число обязано
#: сходиться с тем щупом: расхождение само по себе находка, а не шум.
#: Десять франшиз ТЗ §8, названные ТАК ЖЕ, как их называет само ТЗ. Именем франшизы, а
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
#: Чем плитка называет себя НЕ кино. Приметы прибора, а не продукта, и потому короткие:
#: сюда попадает лишь то, что в титуле картины не стоит никогда - платформа, сцен-метка
#: перевыпуска, формат звука, книги. Замер 07-09-2026: «Mortal Kombat 1 ... PC | RePack»
#: приезжал на «Новинки» плиткой фильма, и ни один из четырнадцати пунктов этого не видел.
_JUNK_RE: Final = re.compile(
    r"(?i)(?<![a-z])(repack|gog-rip|steam-rip|flac|mp3|ape|epub|fb2|djvu|apk|"
    r"artbook|artbuk|wallpapers?)(?![a-z])|\|\s*pc\b|\bpc\s*[|]"
)

_PARTIAL_WAIT: Final = 30.0
#: Сериал для пункта 7. Карточка фильма из пункта 3 серий не содержит по устройству
#: продукта, и судить по ней список серий - вечная краснота независимо от кода. Замер
#: 06-09-2026 на стенде: у этого имени разбирается первый сезон целиком, 7 серий.
#: Фильм приёмки: его ищет пункт 2, его же карточку открывают пункты 3 и 6.
_MOVIE_TITLE: Final = "Интерстеллар"
_SERIES_TITLE: Final = "Во все тяжкие"
#: Сколько ждать тело карточки, открытой кликом: карточка едет по сети, и нажимать
#: стрелки по скелету значит мерить скорость сети, а не навигацию. Замер 06-09-2026 на
#: стенде: у сериала разбор раздачи в TorrServer доезжает за 25-30 с, у фильма - сразу.
_CARD_READY_WAIT: Final = 45000.0
#: Сколько ждать первый кадр после «Играть». Продукт успевает найти раздачу, снять
#: метаданные роя и упаковать первые куски: замер на стенде `.104` дал 10 с до
#: `readyState 4`, порог взят с запасом на холодный рой.
_PLAY_START_WAIT: Final = 90000.0
#: Плитка, которую можно открыть. Пока полка не доехала, страница рисует СКЕЛЕТЫ тем же
#: `data-tc-tile`, и первый узел в DOM обычно как раз скелет: у него нет ни обработчика,
#: ни фокуса, и клик по нему не делает ничего (замер на стенде `.104`, 14 скелетов).
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


@dataclass(slots=True)
class Result:
    """Итог одного пункта §11: число и слово, чем именно недоволен прибор."""

    number: int
    name: str
    ok: bool
    blocked: str | None
    detail: str


@dataclass(slots=True)
class Ctx:
    """Общее для проверок: адрес стенда, открытая страница, флаги и словарь надписей."""

    base: str
    page: Any
    receiver: str
    allow_play: bool
    shots: Path
    english: dict[str, str]


def _get(url: str, timeout: float = 10.0) -> tuple[int, bytes]:
    """GET чистым ``urllib``: прибор не тянет ``requests`` в венв CT502."""
    request = urllib.request.Request(url, headers={"User-Agent": "web-acceptance"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except urllib.error.URLError as error:
        return 0, str(error.reason).encode("utf-8")


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
    """Похоже ли содержимое литерала на текст человеку, а не на служебный токен."""
    if not any(ch.isalpha() for ch in text):
        return False
    if _KEY_RE.match(text):
        return False
    if " " not in text:
        return False
    return not _CLASS_LIST_RE.match(text)


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


def check_1_home(ctx: Ctx) -> Result:
    """Главная поднимается: `GET /` 200, три полки в DOM, `/api/shelves` даёт ≥20 плиток."""
    code, _ = _get(ctx.base + "/")
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_timeout(300)
    found = []
    for key in _SHELF_KEYS:
        text = ctx.english.get(key, "")
        count = ctx.page.get_by_text(text, exact=True).count() if text else 0
        found.append((key, count))
    shelves_seen = sum(1 for _, c in found if c > 0)
    shelves_code, shelves_body = _get(ctx.base + "/api/shelves")
    tiles_ok = False
    shelves_detail = f"GET /api/shelves -> {shelves_code}"
    if shelves_code == 200:
        try:
            payload = json.loads(shelves_body)
        except json.JSONDecodeError as exc:
            shelves_detail += f", тело не JSON: {exc}"
        else:
            counts = _shelf_tile_counts(payload)
            shelves_detail += f", полок {len(counts)}, плиток {counts}"
            # ТЗ §11 п.1: три полки - в DOM, а выдача даёт >=20 плиток в КАЖДОЙ своей
            # полке. Полка «Продолжить» живёт из закладок и на чистом стенде пуста
            # законно: требовать её от выдачи значило бы мерить историю, а не главную.
            tiles_ok = bool(counts) and all(n >= 20 for n in counts.values())
    ok = code == 200 and shelves_seen == 3 and tiles_ok
    by_key = ", ".join(f"{k.rsplit('.', 1)[-1]}={c}" for k, c in found)
    detail = f"GET / -> {code}; полок в DOM по тексту {shelves_seen}/3 ({by_key}); {shelves_detail}"
    return Result(1, "Главная", ok, None, detail)


def _shelf_tiles(payload: Any) -> dict[str, list[dict[str, Any]]]:
    """Сами плитки по полкам из `/api/shelves`, в тех же двух формах ответа."""
    shelves: dict[str, list[dict[str, Any]]] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            tiles = value if isinstance(value, list) else (value or {}).get("tiles")
            if isinstance(tiles, list):
                shelves[str(key)] = [one for one in tiles if isinstance(one, dict)]
    return {key: tiles for key, tiles in shelves.items() if tiles}


def check_15_posters(base: str) -> Result:
    """Обложки: доля плиток с картинкой не ниже 60% в каждой непустой полке (ТЗ §9).

    Планка §9 своего номера в таблице §11 не получила, и мерить её было нечем: пункт 1
    считает ПЛИТКИ, а не картинки на них. Полка из одних букв - законный вид главной по
    всем четырнадцати пунктам, и первым это увидел бы человек, а не прибор.

    Доля считается по ПЕРВЫМ 30 плиткам, тем же окном, каким §9 меряет мусор: столько
    видно на экране, а хвост полки человек листает уже зная, что показывают.
    """
    code, body = _get(base + "/api/shelves")
    if code != 200:
        return Result(15, "Обложки", False, None, f"GET /api/shelves -> {code}")
    try:
        shelves = _shelf_tiles(json.loads(body))
    except json.JSONDecodeError as exc:
        return Result(15, "Обложки", False, None, f"тело не JSON: {exc}")
    shares: dict[str, str] = {}
    ok = bool(shelves)
    for key, tiles in shelves.items():
        head = tiles[:_SHELF_WINDOW]
        with_poster = sum(1 for one in head if str(one.get("poster") or ""))
        shares[key] = f"{with_poster}/{len(head)}"
        if with_poster < _POSTER_BAR * len(head):
            ok = False
    return Result(15, "Обложки", ok, None, f"планка {_POSTER_BAR:.0%}, по полкам {shares}")


def check_16_junk(base: str) -> Result:
    """Мусор: ни одной не-киношной плитки в первых 30 каждой полки (ТЗ §9).

    Приметы тут СВОИ, а не продуктовые: прибор, спрашивающий продукт его же правилом,
    подтверждал бы, что правило применилось, а не что мусора нет. Продукт отсеивает по
    имени РАЗДАЧИ, прибор смотрит на титул готовой ПЛИТКИ - разные концы тракта, и
    «Mortal Kombat ... PC | RePack» проехал бы первый и остался виден второму.
    """
    code, body = _get(base + "/api/shelves")
    if code != 200:
        return Result(16, "Мусор", False, None, f"GET /api/shelves -> {code}")
    try:
        shelves = _shelf_tiles(json.loads(body))
    except json.JSONDecodeError as exc:
        return Result(16, "Мусор", False, None, f"тело не JSON: {exc}")
    caught: list[str] = []
    for key, tiles in shelves.items():
        for one in tiles[:_SHELF_WINDOW]:
            title = f"{one.get('title') or ''} {one.get('original') or ''}"
            found = _JUNK_RE.search(title)
            if found:
                caught.append(f"{key}: {title.strip()!r} по слову {found.group()!r}")
    return Result(16, "Мусор", not caught, None, "; ".join(caught) if caught else "мусора нет")


def check_2_search(ctx: Ctx) -> Result:
    """Поиск: «Интерстеллар» → плитка с 2014 в первых трёх за ≤15 с."""
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
    # голая цифра на экране не значила бы ничего. Прибор ищет ЧИСЛО внутри строки.
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
    ``pointer-events: none`` (ТЗ §4.5): клик по её кнопке перехватывает `<video>`, и
    прибор без движения мышью получал таймаут вместо ответа продукта.
    """
    box = ctx.page.viewport_size or {"width": 1280, "height": 720}
    ctx.page.mouse.move(box["width"] / 2, box["height"] / 2)
    ctx.page.mouse.move(box["width"] / 2 + 8, box["height"] / 2 + 8)
    ctx.page.wait_for_timeout(100)


def _playback_guard(
    number: int, name: str, ctx: Ctx, prev_ok: bool, prev_reason: str
) -> Result | None:
    """Общий тормоз показа (пункты 4, 6, 8-10): чинить нечего - идти некуда без прошлого шага."""
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
    # ТЗ просит ход монотонный и без провала длиннее 3 с. Требовать прироста в КАЖДОЙ
    # секундной паре строже написанного: ровно на то и дан допуск провала, а откат назад
    # (пара с убылью) допуском не покрыт ничем.
    ok = total > 0 and dropped == 0 and worst_stall <= 3.0
    detail = (
        f"{samples} замеров за 60 с, ход {last - first:.1f} с, растущих пар {grew}/{total}, "
        f"пар с откатом {dropped}, худший провал {worst_stall:.1f} с"
    )
    return Result(4, "Показ", ok, None, detail)


#: Куда прибор ставит показ перед остановкой, секунды от начала КАРТИНЫ.
_BOOKMARK_AT: Final = 90.0
#: Сколько ждать, пока закладка догонит остановленную вкладку, секунды. Вкладка шлёт
#: место раз в ``TCPlayer.POSITION_MS`` (2 с), а сторож кладёт его в запись раз в
#: :data:`torrcast.usecases.watch.WATCH_SECONDS` (10 с) - полсекунды тут мерили такт.
_BOOKMARK_WAIT: Final = 30.0


def check_5_bookmark(ctx: Ctx, play_ok: bool) -> Result:
    """Закладка: стоп на 90-й секунде → `WatchState`/`/api/state` даёт `pos` в 90±3.

    🔴 До 90-й секунды показ ПЕРЕМАТЫВАЕТСЯ, а не досиживается. Поток - полносеточный
    VOD всей картины, и `currentTime` у него считает от начала КАРТИНЫ, а не от начала
    показа: поднявшись с прежней закладки (замер 07-09-2026 на стенде `.104`: «Интерстеллар»
    поехал с 410,9 с), вкладка уже на первом же круге больше девяноста - прибор мерил
    место старой закладки и звал это провалом продукта.
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
    # звать дефектом ту раскладку, которую ТЗ §4.3 и задаёт.
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
    (замер 07-09-2026: пункт держался красным на «Интерстелларе» и звал это дефектом).
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
    while time.monotonic() - began < 20.0 and overlay.count() == 0:
        ctx.page.wait_for_timeout(300)
    if overlay.count() == 0:
        return Result(8, "Автопереход", False, None, "плашка [data-tc-next-episode] не появилась")
    before_code, before_body = _get(ctx.base + "/api/state")
    ctx.page.wait_for_timeout(10_000)
    after_code, after_body = _get(ctx.base + "/api/state")
    ok = before_code == 200 and after_code == 200 and before_body != after_body
    detail = f"плашка появилась; /api/state до {before_code} и после {after_code} различаются: {ok}"
    return Result(8, "Автопереход", ok, None, detail)


def check_9_on_tv(ctx: Ctx, play_ok: bool) -> Result:
    """На ТВ: приёмник играет тот же url, позиция растёт, muted, громкость слушается."""
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
    code_a, body_a = _get(ctx.base + "/api/state")
    ctx.page.wait_for_timeout(2000)
    code_b, body_b = _get(ctx.base + "/api/state")
    tv_running = False
    if code_a == 200 and code_b == 200:
        try:
            state_a, state_b = json.loads(body_a), json.loads(body_b)
            tv_running = state_a.get("tv") == ctx.receiver and state_b.get(
                "position", 0
            ) > state_a.get("position", 0)
        except json.JSONDecodeError:
            pass
    ok = muted and tv_running
    detail = f"muted={muted}, /api/state tv растёт между снимками: {tv_running}"
    return Result(9, "На ТВ", ok, None, detail)


def check_10_on_pc(ctx: Ctx, on_tv_ok: bool) -> Result:
    """На комп: приёмник остановлен, muted снят, разрыв позиции ≤5 с."""
    if not on_tv_ok:
        return Result(10, "На комп", False, "пункт 9 (на ТВ не снят)", "возвращать не от чего")
    label = ctx.english.get("web.player.back_to_browser", "")
    button = ctx.page.get_by_text(label, exact=True) if label else None
    if button is None or button.count() == 0:
        return Result(10, "На комп", False, None, f"кнопка {label!r} не найдена")
    code_before, body_before = _get(ctx.base + "/api/state")
    _wake_panel(ctx)
    button.first.click()
    ctx.page.wait_for_timeout(2000)
    shown = _video(ctx, "v => v.muted")
    if shown is None:
        return Result(10, "На комп", False, None, "после «На комп» на странице нет `<video>`")
    muted = bool(shown)
    current = float(_video(ctx, "v => v.currentTime") or 0.0)
    tv_position = None
    if code_before == 200:
        with contextlib.suppress(json.JSONDecodeError):
            tv_position = json.loads(body_before).get("position")
    gap = abs(current - tv_position) if isinstance(tv_position, int | float) else None
    ok = not muted and gap is not None and gap <= 5.0
    detail = f"muted={muted}, currentTime={current:.1f}, разрыв с ТВ-позицией: {gap}"
    return Result(10, "На комп", ok, None, detail)


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
    четвёртым нажатием и уходил пятым, показ не стартовал ни разу за 12). Прибор мерил
    бы тогда свой круг клавиш, а не путь, который проходит зритель.
    """
    if focus["play"] or focus["tile"]:
        return "Enter"
    # Из поля ввода вправо уезжает КАРЕТКА, а не фокус: наружу поле отпускает вниз.
    # Так же и упёршийся в край строки: следующая полка - под ней.
    return "ArrowDown" if focus["field"] or stuck else "ArrowRight"


def check_11_arrows(ctx: Ctx) -> Result:
    """Стрелки: от поля поиска до старта показа за ≤12 нажатий, фокус виден на кадре."""
    # Полосу упаковки тут НЕ освобождают нарочно: предыдущие пункты оставляют показ, и
    # ТЗ §7.4 велит новой «Играть» СНИМАТЬ идущий. Освободить её прибором значило бы
    # снять с продукта ровно то требование, ради которого пункт и меряет старт показа.
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
    # 12-е нажатие стартовало бы показ - тем же риском для полосы упаковки, что и
    # `--play`; без него прибор останавливается на 11-м. Судить его при этом по старту
    # показа значило бы держать пункт вечно красным независимо от продукта: без `--play`
    # проверяемое утверждение - «стрелки ДОВЕЛИ до кнопки «Играть» за 11 нажатий», а
    # 12-е нажатие по ней очевидно и есть старт.
    limit = 11 if not ctx.allow_play else 12
    for i in range(limit):
        was = _focus_of(ctx)
        key = _dpad_key(was, stuck)
        ctx.page.keyboard.press(key)
        ctx.page.wait_for_timeout(150)
        # Enter на плитке уводит на карточку, а она едет по сети. Стрелка по скелету
        # никуда не ведёт не потому, что навигация плоха, а потому, что кнопок ещё нет:
        # мера пункта - НАЖАТИЯ, а не миллисекунды, и ждать тело тут честно.
        _await_card(ctx)
        ctx.page.screenshot(path=str(ctx.shots / f"arrow-{i:02d}.png"))
        active = _focus_of(ctx)
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
    ok = started if ctx.allow_play else reached_play
    goal = "показ стартовал" if ctx.allow_play else "фокус дошёл до «Играть»"
    got = started if ctx.allow_play else reached_play
    stop_note = "" if ctx.allow_play else " (--play не задан: пункт судится по фокусу)"
    detail = f"нажатий {len(steps)}/{limit}, кадры в {ctx.shots}, {goal}: {got}{stop_note}"
    return Result(11, "Стрелки", ok, None, "; ".join(steps) + " | " + detail)


def check_12_franchise(base: str) -> Result:
    """Франшиза: 8 из 10 полок родни (ТЗ §8) непусты - полем ``related`` карточки.

    Шов родни на веб-поверхности один: карточка картины отдаёт полку в ``related``
    (:mod:`web.related_lookup`). Отдельного маршрута франшизы нет и не задумано, поэтому
    прибор идёт тем же путём, что и страница: поиск по названию даёт ключ, ключ даёт
    карточку. Родня приезжает фоном, значит ждать её надо по ``X-Torrcast-Partial``.
    """
    non_empty = 0
    sizes: list[str] = []
    for title in _FRANCHISE_TITLES:
        card = _card_of(base, title)
        kin = card.get("related") if isinstance(card, dict) else None
        size = len(kin) if isinstance(kin, list) else 0
        non_empty += size > 0
        sizes.append(f"{title.split()[0]}={size if isinstance(kin, list) else 'нет'}")
    ok = non_empty >= 8
    detail = f"непустых полок {non_empty} из {len(_FRANCHISE_TITLES)}; " + ", ".join(sizes)
    return Result(12, "Франшиза", ok, None, detail)


def check_13_texts(base: str) -> Result:
    """Тексты: нет литералов человеку в static/*, все ключи app.js в каталоге, ru = набор."""
    en_code, en_body = _get(base + "/api/phrases")
    ru_code, ru_body = _get(base + "/api/phrases?lang=ru")
    english = json.loads(en_body) if en_code == 200 else {}
    russian = json.loads(ru_body) if ru_code == 200 else {}
    same_keys = en_code == 200 and ru_code == 200 and set(english) == set(russian)

    referenced: set[str] = set()
    for name in ("app.js", "player.js"):
        code, body = _get(base + f"/static/{name}")
        if code == 200:
            referenced |= set(_SAY_KEY_RE.findall(body.decode("utf-8", "replace")))
    missing_keys = sorted(referenced - set(english))

    suspects: list[str] = []
    for name in ("app.js", "player.js"):
        code, body = _get(base + f"/static/{name}")
        if code != 200:
            continue
        for lineno, line in enumerate(body.decode("utf-8", "replace").splitlines(), start=1):
            for match in _STRING_RE.finditer(line):
                if _is_prose(match.group(2)):
                    suspects.append(f"{name}:{lineno}:{match.group(2)!r}")

    css_suspects: list[str] = []
    for name in ("style.css", "player.css"):
        code, body = _get(base + f"/static/{name}")
        if code != 200:
            continue
        for lineno, line in enumerate(body.decode("utf-8", "replace").splitlines(), start=1):
            for match in _CONTENT_PROP_RE.finditer(line):
                if any(ch.isalpha() for ch in match.group(2)):
                    css_suspects.append(f"{name}:{lineno}:{match.group(2)!r}")

    ok = same_keys and not missing_keys and not suspects and not css_suspects
    detail = (
        f"EN ключей {len(english)} (код {en_code}), RU ключей {len(russian)} (код {ru_code}), "
        f"наборы {'совпадают' if same_keys else 'РАСХОДЯТСЯ'}; "
        f"ключей из app.js/player.js {len(referenced)}, вне каталога: {missing_keys or 'нет'}; "
        f"JS-литералов человеку: {len(suspects)} {suspects}; "
        f"CSS content-литералов: {len(css_suspects)} {css_suspects}"
    )
    return Result(13, "Тексты", ok, None, detail)


def check_14_gate(repo: Path) -> Result:
    """Гейт: полный `scripts/test-gate` зелёный на холодном венве, там, где лежит репа."""
    script = repo / "scripts" / "test-gate"
    if not script.exists():
        detail = f"{script} не найден - на этом хосте гейт не гоняется отсюда"
        return Result(14, "Гейт", False, f"нет репозитория по --repo {repo}", detail)
    missing = [tool for tool in ("jq", "uv", "ffmpeg") if shutil.which(tool) is None]
    if missing:
        # Прибор живёт на машине с браузером (CT502), а гейт - на машине с деревом и
        # инструментами. Красный тут значил бы «продукт сломан», хотя сломана площадка.
        detail = f"на этой машине нет {', '.join(missing)}: гейт гоняется там, где дерево"
        return Result(14, "Гейт", False, "гейт нечем гонять с этого хоста", detail)
    began = time.monotonic()
    proc = subprocess.run([str(script)], cwd=str(repo), capture_output=True, text=True)
    spent = time.monotonic() - began
    tail = "\n".join((proc.stdout + proc.stderr).splitlines()[-25:])
    ok = proc.returncode == 0
    detail = f"rc={proc.returncode} за {spent:.1f} с; хвост:\n{tail}"
    return Result(14, "Гейт", ok, None, detail)


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

    07-09-2026 прогон дошёл до девятого пункта и умер на `<video>`, которого не было в
    DOM: тринадцать остальных приговоров пропали вместе с ним, включая уже снятые.
    Приёмка обязана назвать их все - иначе она не приёмка, а первый отказ.
    """
    try:
        return run()
    except Exception as error:  # прибору не дано права уронить прогон целиком
        return Result(number, name, False, None, f"прибор упал: {type(error).__name__}: {error}")


def _video(ctx: Ctx, expr: str) -> Any:
    """Спросить `<video>`, если он есть; нет его - `None`, а не падение прибора."""
    if ctx.page.locator("video").count() == 0:
        return None
    return ctx.page.eval_on_selector("video", expr)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://192.168.1.104:8479", help="адрес стенда")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parent.parent)
    parser.add_argument("--receiver", default="192.168.1.90", help="адрес Chromecast приёмника")
    parser.add_argument(
        "--play",
        action="store_true",
        help="разрешить настоящий показ (пп. 4,6,8-11) - отнимает полосу упаковки у соседа",
    )
    parser.add_argument("--shots", type=Path, default=Path("/tmp/web-acceptance-shots"))
    args = parser.parse_args()

    en_code, en_body = _get(args.base + "/api/phrases")
    english = json.loads(en_body) if en_code == 200 else {}

    results: list[Result] = []
    from playwright.sync_api import sync_playwright

    with sync_playwright() as driver:
        browser = driver.chromium.launch(headless=True)
        page = browser.new_page()
        ctx = Ctx(args.base, page, args.receiver, args.play, args.shots, english)
        r1 = _guarded(1, "Главная", lambda: check_1_home(ctx))
        r2 = _guarded(2, "Поиск", lambda: check_2_search(ctx))
        r3 = _guarded(3, "Карточка", lambda: check_3_card(ctx, r2.ok))
        r4 = _guarded(4, "Показ", lambda: check_4_playback(ctx, r3.ok))
        r5 = _guarded(5, "Закладка", lambda: check_5_bookmark(ctx, r4.ok))
        r6 = _guarded(6, "Сначала", lambda: check_6_restart(ctx, r5.ok))
        r7 = _guarded(7, "Сериал", lambda: check_7_series(ctx, r3.ok))
        r8 = _guarded(8, "Автопереход", lambda: check_8_autoplay(ctx, r7.ok))
        r9 = _guarded(9, "На ТВ", lambda: check_9_on_tv(ctx, r4.ok or r7.ok))
        r10 = _guarded(10, "На комп", lambda: check_10_on_pc(ctx, r9.ok))
        r11 = _guarded(11, "Стрелки", lambda: check_11_arrows(ctx))
        results += [r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r11]
        browser.close()

    results.append(_guarded(15, "Обложки", lambda: check_15_posters(args.base)))
    results.append(_guarded(16, "Мусор", lambda: check_16_junk(args.base)))
    results.append(_guarded(12, "Франшиза", lambda: check_12_franchise(args.base)))
    results.append(_guarded(13, "Тексты", lambda: check_13_texts(args.base)))
    results.append(_guarded(14, "Гейт", lambda: check_14_gate(args.repo)))
    return _print(results)


if __name__ == "__main__":
    raise SystemExit(main())
