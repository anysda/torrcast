"""Политика кэша справки: чем ряд становится на диске и когда он ещё свежий.

Зовёт её хранилище справки (:mod:`torrcast.adapters.wiki.facts_file_cache`): само оно
умеет только читать и писать словарь, а что в этом словаре значит «спрашивали, и нет
ответа» и когда такой ряд протух, решают правила отсюда.
"""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.minutes_of import minutes_of
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import EMPTY_TTL, FACTS_RULES, RUNTIME_CAP_MINUTES
from torrcast.domain.json_value import JsonValue


def _key(title: str, year: int | None) -> str:
    return f"{title}|{year if year is not None else ''}"


def _origin_key(title: str, series: bool | None) -> str:
    """Паспорта лежат в том же файле, что и справка, но в своём ряду ключей."""
    kind = "either" if series is None else "tv" if series else "movie"
    return f"origin|{kind}|{title}"


def _row_origin(row: JsonValue) -> Origin | None:
    """Ряд кэша в паспорт. ``None`` — не спрашивали; пустой паспорт — спрашивали, нет его."""
    if not isinstance(row, dict):
        return None
    shown = row.get("year")
    return Origin(
        title=str(row.get("title", "")),
        year=shown if isinstance(shown, int) else None,
        name=str(row.get("name", "")),
        entity=str(row.get("entity", "")),
        guessed=bool(row.get("guessed")),
        # Ряды, записанные до TC-567, доказательства происхождения не носят: отсутствие
        # отметки честно значит «неизвестно», и выдавать её за доказанное нельзя.
        native=bool(row.get("native")),
        namesake=str(row.get("namesake", "")),
        # Ряды, записанные до TC-450, отметки об источнике не носят: пустая строка честно
        # значит «неизвестно», и выдавать её за Википедию нельзя.
        source=str(row.get("source", "")),
    )


def _origin_row(found: Origin) -> dict[str, JsonValue]:
    """Паспорт в ряд кэша: на диск едет всё, чего второму показу иначе не узнать."""
    return {
        "title": found.title,
        "year": found.year,
        "name": found.name,
        # Q-идентификатор нужен на диске, иначе одинокий год (:func:`origin_either`) на
        # втором показе терял бы второй источник и ронял год, подтверждённый на первом.
        "entity": found.entity,
        # Отметка «имя лишь похоже» тоже нужна на диске: без неё гейт добора на втором
        # показе той же картины поверил бы догадке как доказанному имени.
        "guessed": found.guessed,
        # 🔴 TC-567. Доказательство отечественного происхождения читается из статьи, а со
        # второго показа справку не спрашивают вовсе: не окажись его на диске, собственная
        # дорожка картины теряла бы своё место у всех, кроме самого первого зрителя.
        "native": found.native,
        # Тёзка того же года (TC-371) - тоже на диск: со второго показа справку не
        # спрашивают вовсе, и честная строка про двусмысленность иначе пропадала бы.
        "namesake": found.namesake,
        # 🔴 TC-450. ЧЕМ отвечено - на диск вместе с ответом, иначе сохранённый прогон
        # умеет сказать только «оригинал есть», а «его дала карта, а не Википедия» - уже
        # нет, и пользу карты нечем сосчитать. На показ поле не влияет.
        "source": found.source,
    }


def _cached_facts(
    raw: Mapping[str, JsonValue], wanted: list[tuple[str, int | None]], now: float
) -> dict[tuple[str, int | None], Fact]:
    """Что из лежащего на диске годится сейчас. Битый ряд — как пустой: спросим сеть.

    🔴 Годится только ряд, снятый НЫНЕШНИМИ правилами (:data:`FACTS_RULES`): полка живёт
    дольше правил, и ряд прежнего номера - как и ряд кода, который номера ещё не писал, -
    судится заново, что бы в нём ни лежало. Иначе отказ, купленный дефектом разбора,
    молчал бы весь свой срок уже после починки дефекта, а находка прежних правил не
    пересуживалась бы никогда.

    Ряд с отметкой ``empty`` — это записанное «справки нет»: картина отдаётся пустой, и в
    сеть за ней не идут. Отметка со сроком (:data:`EMPTY_TTL`): вышел — ряда как не было.

    Хронометраж вне правдоподобных границ (:data:`RUNTIME_CAP_MINUTES`) с ряда снимается:
    срока у найденного ряда нет вовсе, и однажды записанная выдумка иначе печаталась бы
    человеку вечно. Остальное в ряду при этом остаётся - описание и рейтинг не виноваты.
    """
    out: dict[tuple[str, int | None], Fact] = {}
    for key in wanted:
        row = raw.get(_key(*key))
        if not isinstance(row, dict):
            continue
        if row.get("rules") != FACTS_RULES:
            continue
        blank = row.get("empty")
        if isinstance(blank, int | float) and now - blank > EMPTY_TTL:
            continue
        runtime = str(row.get("runtime", ""))
        fact = Fact(
            about=str(row.get("about", "")),
            rating=str(row.get("rating", "")),
            runtime="" if minutes_of(runtime) > RUNTIME_CAP_MINUTES else runtime,
        )
        if not fact and not isinstance(blank, int | float):
            continue
        out[key] = fact
    return out


def _fact_rows(
    found: dict[tuple[str, int | None], Fact],
    misses: list[tuple[str, int | None]],
    now: int,
) -> dict[str, JsonValue]:
    """Итог похода в ряды кэша; ничего не добыто и не опровергнуто — писать нечего.

    Каждый ряд метится номером правил, которыми он снят (:data:`FACTS_RULES`), - по нему
    читающая сторона отличает ряд нынешних правил от ряда прежних и пересуживает только
    второй (:func:`_cached_facts`).

    ``misses`` — картины, про которые источник ответил, но сказать ему нечего. Раньше они
    в кэш не попадали вовсе, и каждое меню шло за ними в сеть заново: поход не успевал к
    дедлайну, меню печаталось голым, следующее — точно так же. Пустой ответ — тоже ответ,
    и он тоже помнится, только со сроком (:data:`EMPTY_TTL`).
    """
    rows: dict[str, JsonValue] = {}
    for key, fact in found.items():
        rows[_key(*key)] = {
            "about": fact.about,
            "rating": fact.rating,
            "runtime": fact.runtime,
            "rules": FACTS_RULES,
        }
    for key in misses:
        rows[_key(*key)] = {
            "about": "",
            "rating": "",
            "runtime": "",
            "empty": now,
            "rules": FACTS_RULES,
        }
    return rows
