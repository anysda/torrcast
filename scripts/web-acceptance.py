#!/usr/bin/env python3
"""Приёмочная проверка веб-показа: шестнадцать пунктов, каждый - число, а не «открылось».

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
``data-tc-episode``, плеер - ``data-tc-audio-option`` и ``data-tc-next-episode``.
Заголовки полок и кнопки проверка ищет по ТЕКСТУ из ``/api/phrases`` - это переживёт
смену разметки, а не переживёт смену каталога.

⚠️ Пункт 13 - грепом, а не разбором AST: однословный литерал (``'Play'``) от ключа
каталога не отличить простым грепом по кавычкам. Это названный предел точности этой
проверки, а не дыра, которую прячут.
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
from collections.abc import Callable
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
    """Главная сверяет «Продолжить» с историей, а две полки выдачи - с API."""
    code, _ = _get(ctx.base + "/")
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
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
            tiles_ok = set(counts) == {"fresh", "popular"} and all(n >= 20 for n in counts.values())
    history_ok = history_count is not None and (
        (history_count == 0 and continue_seen == 0)
        or (history_count > 0 and continue_seen == 1 and continue_tiles == history_count)
    )
    basics_seen = sum(1 for _, count in found if count > 0)
    ok = code == 200 and basics_seen == 2 and history_ok and tiles_ok
    by_key = ", ".join(f"{k.rsplit('.', 1)[-1]}={c}" for k, c in found)
    detail = (
        f"GET / -> {code}; полки выдачи в DOM по тексту {basics_seen}/2 ({by_key}); "
        f"continue_watching={continue_seen}, плиток {continue_tiles}; {history_detail}; "
        f"{shelves_detail}"
    )
    return Result(1, "Главная", ok, None, detail)


def check_17_wheel(ctx: Ctx) -> Result:
    """Колесо мыши: вертикальный скролл над полкой едет вбок, мимо полки - листает страницу.

    Пункт сперва ищет полку, которой правда есть куда ехать (`scrollWidth > clientWidth`):
    без такой полки испытывать нечего, и это говорится словом, а не тонет в зелёном OK.
    Отрицательная проба - тем же прогоном: то же самое колесо ВНЕ полки обязано листать
    страницу и не трогать `scrollLeft` полки, которую только что сдвинуло.
    """
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_timeout(300)
    row = ctx.page.evaluate(
        """
        () => {
            const rows = Array.from(document.querySelectorAll('.tc-row'));
            const row = rows.find(r => r.scrollWidth > r.clientWidth);
            if (!row) return null;
            row.scrollIntoView({ block: 'center' });
            const rect = row.getBoundingClientRect();
            return {
                index: rows.indexOf(row),
                x: rect.x + rect.width / 2,
                y: rect.y + rect.height / 2,
                scrollLeft: row.scrollLeft,
            };
        }
        """
    )
    if row is None:
        detail = (
            "ни одна полка не переполнена по ширине "
            "(scrollWidth <= clientWidth) - колесу негде ехать вбок"
        )
        return Result(17, "Колесо", False, "нет переполненной полки", detail)

    before = int(row["scrollLeft"])
    ctx.page.mouse.move(row["x"], row["y"])
    ctx.page.mouse.wheel(0, 240)
    ctx.page.wait_for_timeout(100)
    over_row = int(
        ctx.page.evaluate("(i) => document.querySelectorAll('.tc-row')[i].scrollLeft", row["index"])
    )

    # Отрицательная проба: то же колесо, но указатель НЕ над полкой.
    ctx.page.evaluate("() => window.scrollTo(0, 0)")
    page_before = int(ctx.page.evaluate("() => window.scrollY"))
    outside = ctx.page.evaluate(
        """
        () => {
            const el = document.querySelector('.tc-search') || document.body;
            const rect = el.getBoundingClientRect();
            return { x: rect.x + 10, y: Math.max(5, rect.y + 5) };
        }
        """
    )
    ctx.page.mouse.move(outside["x"], outside["y"])
    ctx.page.mouse.wheel(0, 300)
    ctx.page.wait_for_timeout(100)
    page_after = int(ctx.page.evaluate("() => window.scrollY"))
    row_after_outside = int(
        ctx.page.evaluate("(i) => document.querySelectorAll('.tc-row')[i].scrollLeft", row["index"])
    )

    row_moved = over_row > before
    page_moved = page_after > page_before
    row_untouched = row_after_outside == over_row
    ok = row_moved and page_moved and row_untouched
    detail = (
        f"над полкой[{row['index']}]: scrollLeft {before} -> {over_row}; "
        f"мимо полки: window.scrollY {page_before} -> {page_after}, "
        f"scrollLeft полки не тронут ({over_row} -> {row_after_outside})"
    )
    return Result(17, "Колесо", ok, None, detail)


def check_18_caption_scroll(ctx: Ctx) -> Result:
    """Автопрокрутка подписи: настоящая переполненная подпись едет вниз и обратно при наведении.

    Пункт сперва ищет на живой полке плитку, чья НАСТОЯЩАЯ подпись после разворота
    (`is-lit`) не влезает в отведённые две строки. Синтетическую подпись он себе не
    рисует: если такой плитки не нашлось ни одной, это отдельная находка о самой полке,
    а не повод подменить пробу и объявить пункт зелёным.
    """
    ctx.page.goto(ctx.base + "/", wait_until="load", timeout=15000)
    ctx.page.wait_for_timeout(300)
    # Наведение теперь раздувает полку («Size hierarchy»: ряд под фокусом 268px), и
    # подпись, не влезавшая в 210px, в раздутой плитке может поместиться - тогда ехать
    # ей нечего и незачем. Переполнение меряется при том же раскладе, что создаёт само
    # наведение: `is-lit` на плитке и `tc-row--focused` на её ряду.
    candidate = ctx.page.evaluate(
        """
        () => {
            const tiles = Array.from(document.querySelectorAll('.tc-tile[data-tc-focusable]'));
            for (let i = 0; i < tiles.length; i++) {
                const tile = tiles[i];
                const box = tile.querySelector('.tc-tile-cap');
                if (!box) continue;
                const row = tile.closest('.tc-row');
                tile.classList.add('is-lit');
                if (row) row.classList.add('tc-row--focused');
                const overflow = box.scrollHeight - box.clientHeight;
                tile.classList.remove('is-lit');
                if (row) row.classList.remove('tc-row--focused');
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

    rect = ctx.page.evaluate(
        """
        (i) => {
            const tile = document.querySelectorAll('.tc-tile[data-tc-focusable]')[i];
            tile.scrollIntoView({ block: 'center' });
            const r = tile.getBoundingClientRect();
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
    """Сами плитки по полкам из `/api/shelves`, в тех же двух формах ответа."""
    shelves: dict[str, list[dict[str, Any]]] = {}
    if isinstance(payload, dict):
        for key, value in payload.items():
            # Не всякое поле ответа - полка: рядом с ними лежит время сборки строкой
            # (`built_at`), и вопрос «а нет ли внутри плиток» валил скрипт целиком.
            tiles = value if isinstance(value, list) else _inner(value)
            if isinstance(tiles, list):
                shelves[str(key)] = [one for one in tiles if isinstance(one, dict)]
    return {key: tiles for key, tiles in shelves.items() if tiles}


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
    ok = bool(shelves)
    for key, tiles in shelves.items():
        head = tiles[:_SHELF_WINDOW]
        with_poster = sum(1 for one in head if str(one.get("poster") or ""))
        shares[key] = f"{with_poster}/{len(head)}"
        if with_poster < _POSTER_BAR * len(head):
            ok = False
    return Result(15, "Обложки", ok, None, f"планка {_POSTER_BAR:.0%}, по полкам {shares}")


def check_16_junk(base: str) -> Result:
    """Мусор: ни одной не-киношной плитки в первых 30 каждой полки.

    Приметы тут СВОИ, а не продуктовые: скрипт, спрашивающий продукт его же правилом,
    подтверждал бы, что правило применилось, а не что мусора нет. Продукт отсеивает по
    имени РАЗДАЧИ, скрипт смотрит на титул готовой ПЛИТКИ - разные концы тракта, и
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
    tiles = shelves.get("fresh") or next(iter(shelves.values()), [])
    if not tiles:
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
    # ТЗ просит ход монотонный и без провала длиннее 3 с. Требовать прироста в КАЖДОЙ
    # секундной паре строже написанного: ровно на то и дан допуск провала, а откат назад
    # (пара с убылью) допуском не покрыт ничем.
    ok = total > 0 and dropped == 0 and worst_stall <= 3.0
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
    before_code, before_body = _get(ctx.base + "/api/state")
    ctx.page.wait_for_timeout(10_000)
    after_code, after_body = _get(ctx.base + "/api/state")
    ok = before_code == 200 and after_code == 200 and before_body != after_body
    detail = f"плашка появилась; /api/state до {before_code} и после {after_code} различаются: {ok}"
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
    if took is not None:
        before = _position(ctx)
        tv_running, grew_in = _await_position_growth(ctx, before)
        volume_ok, volume_detail = _volume_follows_page(ctx)
    ok = muted and tv_running and volume_ok
    waited = "не поднялся" if took is None else f"{took:.0f} с"
    grown = "не сдвинулась" if grew_in is None else f"за {grew_in:.1f} с"
    detail = (
        f"muted={muted}, каст поднялся за {waited}, позиция ТВ выросла {grown}; "
        f"громкость: {volume_detail}"
    )
    return Result(9, "На ТВ", ok, None, detail)


#: Сколько ждать, пока продукт назовёт каст своим: рукопожатие, LOAD и первый кадр.
_TV_WAIT: Final = 60.0

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
    """Франшиза: 8 из 10 полок родни непусты - полем ``related`` карточки.

    Шов родни на веб-поверхности один: карточка картины отдаёт полку в ``related``
    (:mod:`web.related_lookup`). Отдельного маршрута франшизы нет и не задумано, поэтому
    скрипт идёт тем же путём, что и страница: поиск по названию даёт ключ, ключ даёт
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
        # Скрипт живёт на машине с браузером, а гейт - на машине с деревом и
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
        help="разрешить настоящий показ (пп. 4,6-11,20) - отнимает полосу упаковки у соседа",
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
        ctx = Ctx(args.base, page, args.play, args.shots, english)
        r1 = _guarded(1, "Главная", lambda: check_1_home(ctx))
        r17 = _guarded(17, "Колесо", lambda: check_17_wheel(ctx))
        r18 = _guarded(18, "Подпись", lambda: check_18_caption_scroll(ctx))
        r19 = _guarded(19, "Латиница", lambda: check_19_latin_titles(ctx))
        r21 = _guarded(21, "Слияние", lambda: check_21_merge_hits(ctx))
        r2 = _guarded(2, "Поиск", lambda: check_2_search(ctx))
        r3 = _guarded(3, "Карточка", lambda: check_3_card(ctx, r2.ok))
        r4 = _guarded(4, "Показ", lambda: check_4_playback(ctx, r3.ok))
        r5 = _guarded(5, "Закладка", lambda: check_5_bookmark(ctx, r4.ok))
        r6 = _guarded(6, "Сначала", lambda: check_6_restart(ctx, r5.ok))
        r7 = _guarded(7, "Сериал", lambda: check_7_series(ctx, r3.ok))
        r8 = _guarded(8, "Автопереход", lambda: check_8_autoplay(ctx, r7.ok))
        r9 = _guarded(9, "На ТВ", lambda: check_9_on_tv(ctx, r4.ok or r7.ok))
        r10 = _guarded(10, "На комп", lambda: check_10_on_pc(ctx, r9.ok))
        r20 = _guarded(20, "Уход", lambda: check_20_leave_tears_down(ctx, r10.ok))
        r11 = _guarded(11, "Стрелки", lambda: check_11_arrows(ctx))
        results += [r1, r2, r3, r4, r5, r6, r7, r8, r9, r10, r20, r11, r17, r18, r19, r21]
        browser.close()

    results.append(_guarded(15, "Обложки", lambda: check_15_posters(args.base)))
    results.append(_guarded(16, "Мусор", lambda: check_16_junk(args.base)))
    results.append(_guarded(22, "Полка → карточка", lambda: check_22_shelf_cards_open(args.base)))
    results.append(_guarded(12, "Франшиза", lambda: check_12_franchise(args.base)))
    results.append(_guarded(13, "Тексты", lambda: check_13_texts(args.base)))
    results.append(_guarded(14, "Гейт", lambda: check_14_gate(args.repo)))
    return _print(results)


if __name__ == "__main__":
    raise SystemExit(main())
