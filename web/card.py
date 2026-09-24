"""Карточка одной картины: ``GET /api/card/{key}?query=...``.

Ключ адресует картину в круге, который **тем же поиском**, что и ``/api/search``, находит запрос из
строки доводов - карточка не хранит своего пула раздач, а спрашивает его заново. Строке доводов
доверия нет как ЕДИНСТВЕННОМУ доводу: это то, чем плитку открыли, а не имя картины, а в ссылке,
набранной руками, её нет вовсе (:func:`web.own_plan.own_plan`). Описание и рейтинг едут фоновым
добором (:class:`torrcast.usecases.facts.Facts`) и не задерживают ответ: не приехало - поле
``null`` и заголовок ``X-Torrcast-Partial``, страница переспросит сама. Пустое поле недоездом НЕ
считается: заголовок стоит только там, где переспрашивать есть смысл (:func:`_answer`).

Переспрос с ``wait=1`` - долгий: ответ держится, пока тело не изменится или не доедет
целиком, но не дольше :data:`WAIT`. Короткий опрос раз в две секунды бросал страницу после
пятого захода со скелетом вместо описания и слал по 4-6 GET на картину.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Final

from hass.hit_posters import hits
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.torrserver.torr_server import TorrServer
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.domain.spoken_title import spoken_title
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.state_store.slot import store
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.select.plan import Plan
from web.answer import Answer
from web.answered_episode import _episodes_unavailable
from web.card_ask import NO_ASK, CardAsk
from web.card_details import CardDetails
from web.card_poster import CardPoster
from web.card_seasons import card_seasons
from web.card_voices import card_voices
from web.card_warm import CARD_WARM
from web.circle_refusal import circle_refusal
from web.display_runtime import display_runtime
from web.episode_lookup import GRACE, EpisodeLookup
from web.key_name import key_name
from web.own_plan import own_plan
from web.playing_on_tv import playing_on_tv
from web.preview import _facts, _related_of, preview
from web.rating_score import rating_score
from web.refusal import refusal
from web.release_keys import release_keys
from web.request import Request
from web.series_catalog import SERIES
from web.start_related import start_related
from web.voice_lookup import VoiceLookup
from web.warm_wiring import RELATED, WARM

#: Префикс, под которым живёт вся карточка; ключ картины - хвост пути после него.
_PREFIX = "/api/card/"
#: Родня общая с прогревом полок; имя остаётся подменяемым швом карточечных проб.
_related = RELATED
#: Заголовок, которым карточка метит недоехавшее описание, рейтинг, родню или серии.
_PARTIAL = "X-Torrcast-Partial"
#: Потолок долгого переспроса: переживает первый контакт разбора серий с роем, который завёл
#: ещё первый GET. Равные 8 с кончали заход раньше разбора (живой приёмник: Knightfall, 8.19 с).
WAIT: Final = GRACE + 1.0
_TICK: Final = 0.25  # Шаг, которым долгий переспрос оглядывается на фоновые доборы.
#: Разбор серий раздачи, которую играл бы показ (:class:`web.episode_lookup.EpisodeLookup`).
_episodes = EpisodeLookup(engines=TorrServer)
#: Дорожки той раздачи, которую играл бы показ (:class:`web.voice_lookup.VoiceLookup`).
_voices = VoiceLookup(engines=TorrServer, warms=CARD_WARM)
#: Приговор обложки - тот же, что у выдачи поиска и полки (:mod:`web.card_poster`).
_poster = CardPoster(offer=hits.urgent, pending=hits.pending)
#: Сколько долгий заход досиживает после первой перемены, пока доезжает остальное: части
#: приходят порознь (живой приёмник: родня и серии через 2.1 с, обложка через 2.7 с).
_SETTLE: Final = 1.0


def card(request: Request) -> Answer:
    """Собрать карточку по ключу картины, найденной тем же кругом, что и поиск."""
    query = request.query.get("query", "")
    title = request.query.get("title", "").strip()
    key = request.path[len(_PREFIX) :]
    if not query.strip() and not title and not key_name(key):
        return refusal(400, "no_query")
    hint = start_related(request, _facts, _related)
    if early := preview(request, key, WARM, _related):
        return early
    config = load_config()
    try:
        # Живой запрос не ждёт за очередью прогрева: несогретый круг он считает сам.
        plan, pick, found = own_plan(key, query, title, WARM.take)
    except TorrcastError as failed:
        return circle_refusal(failed)
    if plan is None:
        return refusal(404, "not_found")
    wait = WAIT if request.query.get("wait") == "1" else 0.0
    # Дорожки (:func:`_body`) спрашивают по строке, что и нашла картину, не по адресной.
    ask = replace(CardAsk.of(request.query), query=found)
    return _answer(plan, config, pick, wait, hint, ask)


def _answer(
    plan: Plan,
    config: Config,
    pick: int,
    wait: float = 0.0,
    hint: tuple[str, int, str] | None = None,
    ask: CardAsk = NO_ASK,
) -> Answer:
    """Тело ответа плюс заголовок недоехавшей части: справка, обложка, родня, серии.

    Дорожки ответ не держат: их читает отбор раздачи, и это секунды роя, а не справки.
    Тело говорит о них ``voices_pending``, и держит ответ на них только добор ``voices=1``.
    """
    picture = plan.picture
    watch = store().load()
    entry = watch.get(picture.key)
    if hint:
        facts = _facts.of(*hint)
    else:
        facts = MenuFacts([(picture.title, picture.year, picture.kind)], budget=0.0)
        facts.foreground = True
        facts.start()
    until = time.monotonic() + wait
    first, partial = _body(plan, config, pick, entry, facts, playing_on_tv(picture.key), hint, ask)
    body = first
    while (partial or (ask.voices and body.get("voices_pending"))) and time.monotonic() < until:
        time.sleep(_TICK)
        on_tv = playing_on_tv(picture.key)
        body, partial = _body(plan, config, pick, entry, facts, on_tv, hint, ask)
        if body != first:
            until = min(until, time.monotonic() + _SETTLE)
    extra = ((_PARTIAL, "1"),) if partial else ()
    return Answer(200, json.dumps(body, ensure_ascii=False).encode("utf-8"), extra=extra)


def _body(
    plan: Plan,
    config: Config,
    pick: int,
    entry: Entry | None,
    facts: MenuFacts,
    playing: bool,
    hint: tuple[str, int, str] | None = None,
    ask: CardAsk = NO_ASK,
) -> tuple[dict[str, JsonValue], bool]:
    """Тело как оно есть сейчас и «что-то ещё в пути»; пустая справка - готовый ответ."""
    picture = plan.picture
    title, year, kind = hint or (picture.title, picture.year, picture.kind)
    fact = facts.ready(title, year)
    told = facts.answered(title, year)
    url, profile = config.torrserver_url, _voices.profile_of(config)
    seasons, seasons_partial, episode_release, layout = card_seasons(
        plan, entry, url, _episodes, ask.season, profile, SERIES
    )
    series = kind == "tv"
    related = CardDetails.others(
        picture.key, _related_of(_related, title, series, fact, told, year)
    )
    # Родня без идущего похода - молчание источника: ждать нечего, страница не переспрашивает.
    coming = related is None and _related.waiting(title, series)
    poster, judging = _poster.of(picture)
    heard, hearing = _voices.of(plan, ask.query, config, entry) if plan.ranked else (None, False)
    runtime, runtime_estimated = display_runtime(plan, fact)
    body: dict[str, JsonValue] = {
        # Номер картины В КРУГЕ: им «Играть» просит показ ровно ту, которую человек
        # видит, а не ту, что круг взял бы по умолчанию (ТЗ §4.3).
        "pick": pick,
        "picture": picture.key,
        **release_keys(plan, episode_release, heard, WARM.live(ask.query) is not None),
        "title": picture.title,
        "shown": spoken_title(picture.title, picture.original or ""),
        "original": picture.original or None,
        "year": picture.year,
        "kind": picture.kind,
        "runtime": runtime,
        "runtime_estimated": runtime_estimated,
        "rating": rating_score(fact.rating),
        "blurb": fact.about if told else None,
        "poster": poster,
        "voices": card_voices(heard, ask.lang),
        "voices_pending": hearing,
        "resumable": entry.resumable if entry else False,
        "label": entry.label if entry else "",
        "pos": entry.pos if entry else 0.0,  # Место закладки в секундах (TC-1281).
        # Картина идёт НА ТЕЛЕВИЗОРЕ (:func:`web.playing_on_tv.playing_on_tv`): кнопки
        # «Подключиться»/«Завершить» вместо «PLAY ON TV» (:mod:`web.static.card.js`).
        # Показ в самой вкладке сюда не годится: приёмника, к которому подключаются, нет.
        "playing": playing,
        # Машина без ТВ (``config.tv`` пуст) не предлагает показ на ТВ вовсе.
        "tv": bool(config.tv),
        "seasons": seasons,
        "episodes_unavailable": _episodes_unavailable(_episodes, episode_release),
        # Числа серий сезонов списка не как у раздач: строка просит серию сквозным номером.
        "layout": [*layout],
        "related": related,
        "releases_count": len(picture.releases),
        "sources_count": CardDetails.sources_count(picture.releases),
    }
    return body, not told or seasons_partial or coming or judging
