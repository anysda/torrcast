"""Родня картины (другие части франшизы) без ожидания сети: фоновый добор с кэшем.

Тот же приём, что у :class:`web.episode_lookup.EpisodeLookup`: карточка не ждёт
Wikidata, а спрашивает кэш и заводит фон, если его там ещё нет. ``None`` значит
«ещё не готово» и тянет за собой :data:`web.card._PARTIAL`; пустой список -
законченный ответ «родни не нашлось» (§8), а не недоезд.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from hass.hit_posters import hits
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.patterns import _CYRILLIC
from torrcast.domain.facts.settings import SPARQL_TIMEOUT
from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify
from torrcast.domain.spoken_title import spoken_title
from torrcast.usecases.facts import FactPicture

#: Тот же ``FranchiseKin.of``: имя, серия ли картина, срок сети - родня; ``None`` -
#: сеть промолчала, и это НЕ законченный ответ: в кэш ему нельзя, следующий вопрос
#: заводит новый добор (:meth:`RelatedLookup._build`).
Franchise = Callable[[str, bool, float], list[Kin] | None]
#: Тот же ``Passport.of``: паспорт родни латиницей, которого Wikidata не называет (:func:`_seed`).
PassportOf = Callable[[str, bool, float], Origin]
#: Тот же ``HitPosters.offer``: те же записи, с обложкой у тех, кому она нашлась.
Offer = Callable[[list[JsonValue]], list[JsonValue]]
Spawn = Callable[[Callable[[], None]], None]
Warm = Callable[[list[Kin]], object]
TIMEOUT = 8.0
RETRY = 3600.0
#: Сколько молчание источника держит имя от нового похода: ``None`` отдаёт и картина без
#: статьи в Википедии, и без срока каждый тик долгого захода карточки шёл в сеть заново
#: (стенд `.104`, 11-09-2026: четыре фильма полки из пяти, по пять ``GET`` на карточку).
SILENT = 120.0
#: Та же форма, что у плитки полок (:data:`web.shelves_cache._TILE_FIELDS`) - страница
#: рисует обе плитки одним и тем же кодом, а не двумя похожими. ``shown`` - имя ДЛЯ
#: ЧЕЛОВЕКА, ``title`` остаётся записанным ради розыска обложки и ``query``.
_TILE_FIELDS = ("key", "title", "shown", "year", "kind", "quality", "poster", "query")


def _daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True, name="related-lookup").start()


def _no_passport(_title: str, _series: bool, _timeout: float) -> Origin:
    """Паспорт по умолчанию: без проводки родня остаётся под записанным именем."""
    return Origin()


def _no_warm(_kin: list[Kin]) -> None:
    """Пустая проводка: тестовый добор родни не трогает очередь поиска."""
    return None


def _spoken(found: list[Kin]) -> list[Kin]:
    """Без срока Wikidata не играбельна - убираем всегда (TC-1320, бесплатный признак).
    Под русским - живой ``kin.ru`` вместо гадающего запасного (TC-1321); без него и без
    кириллицы вовсе - тоже убираем, не переводим (TC-956, один путь имени)."""
    dated = [kin for kin in found if kin.year is not None]
    if tongue() == EN:
        return dated
    kept = [kin._replace(name=kin.ru) if kin.ru else kin for kin in dated]
    return [kin for kin in kept if _CYRILLIC.search(kin.name)]


def _seed(kin: Kin, original: str) -> dict[str, JsonValue]:
    """Плитка родни до обложки: ``original`` - розыскное поле обложки, а не показа.
    🔴 ``query`` - имя САМОЙ родни: карточка ищет ключ в круге этого запроса
    (:func:`web.card_lookup.card_lookup`); запрос родительской картины отвечал 404 у
    всех соседей «Гарри Поттера» и «Властелина колец» (стенд `.136`)."""
    return {
        "key": f"movie:{slugify(kin.name)}:{kin.year or 0}",
        "title": kin.name,
        "shown": spoken_title(kin.name, original),
        "year": kin.year,
        "kind": "movie",
        "quality": None,
        "query": kin.name,
        "original": original,
    }


def _project(record: JsonValue) -> JsonValue:
    """Ужать плитку под контракт: обложка обещана, а розыскное ``original`` - нет."""
    if not isinstance(record, dict):
        return record
    return {field_name: record.get(field_name) for field_name in _TILE_FIELDS}


@dataclass
class RelatedLookup:
    """Кэш родни на процесс: первый вопрос о картине заводит фон, а не ждёт его."""

    franchise: Franchise
    entity_kin: Callable[[str, float], list[Kin] | None] | None = None
    offer: Offer = hits.offer
    passport: PassportOf = _no_passport
    warm: Warm = _no_warm
    spawn: Spawn = _daemon
    clock: Callable[[], float] = time.monotonic
    _tiles: dict[tuple[str, bool], tuple[list[JsonValue], float]] = field(default_factory=dict)
    _pending: set[tuple[str, bool]] = field(default_factory=set)
    _silent: dict[tuple[str, bool], float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def of(self, title: str, series: bool, entity: str = "") -> list[JsonValue] | None:
        """Полка родни картины; ключ кэша - ровно то, чем полка добыта: имя И тип.

        🔴 Тип в ключе не украшение. Карточка спрашивает полку по имени картины и её
        роду (:mod:`web.card`), а род уходит в паспорт, у которого статья фильма и
        статья сериала разные. Одно имя на два рода - две РАЗНЫЕ полки, и общий ключ
        отдавал одну другой: замер 10-09-2026 на стенде `.104` - у «Чужого» (2021, tv)
        родни нет, и открытая первой его карточка гасила «Чужого» (1979, movie) на
        целый час (:data:`RETRY`), а открытая первой карточка фильма приписывала
        сериалу шесть частей чужой франшизы.
        """
        asked = (title, series)
        now = self.clock()
        with self._lock:
            cached = self._tiles.get(asked)
            if cached is not None and cached[1] > now:
                return cached[0]
            if asked in self._pending or now < self._silent.get(asked, 0.0):
                return None
            self._pending.add(asked)
        self.spawn(lambda: self._build(title, series, entity))
        with self._lock:
            cached = self._tiles.get(asked)
            return cached[0] if cached is not None else None

    def waiting(self, title: str, series: bool) -> bool:
        """Идёт ли поход за роднёй: ``None`` без похода - молчание, ждать его нечего."""
        with self._lock:
            return (title, series) in self._pending

    def retry(self, title: str, series: bool, entity: str = "") -> list[JsonValue] | None:
        """Повторить именно открытой карточкой после неуспеха фонового похода."""
        with self._lock:
            self._silent.pop((title, series), None)
        return self.of(title, series, entity)

    def finish(self, pictures: list[FactPicture]) -> None:
        """Дождаться родни видимой полки, но не дольше одного сетевого срока."""
        asked = [(picture[0], len(picture) == 3 and picture[2] == "tv") for picture in pictures]
        for title, series in asked:
            self.of(title, series)
        until = time.monotonic() + TIMEOUT
        while time.monotonic() < until:
            if not any(self.waiting(title, series) for title, series in asked):
                return
            time.sleep(0.05)

    def _build(self, title: str, series: bool, entity: str = "") -> None:
        """Собрать плитки родни; молчание в кэш не ложится - переспросят после :data:`SILENT`.
        🔴 Пустая полка кэшируется только когда она ОТВЕЧЕНА (:meth:`FranchiseKin.of`
        отдал список): ``None`` - сеть промолчала, и записать «родни нет» на час
        (:data:`RETRY`) гасило бы полку одной оборванной связью (стенд `.104`, 10-09-2026).
        Без ``try/finally`` упавший фон держал имя в ``_pending`` вечно."""
        found: list[Kin] | None = None
        try:
            found = (
                self.entity_kin(entity, SPARQL_TIMEOUT)
                if entity and self.entity_kin
                else self.franchise(title, series, TIMEOUT)
            )
            if found is None:
                return
            found = _spoken(found)
            seeds: list[JsonValue] = [_seed(kin, self._latin_of(kin.name)) for kin in found]
            # Названия и годы уже пришли от Wikidata. Приговор постеров - отдельная сеть,
            # и держать правильную полку до его ответа значило бы платить её при клике.
            tiles = [_project(record) for record in seeds]
            with self._lock:
                self._tiles[(title, series)] = (tiles, self.clock() + RETRY)
            self.warm(found)
            tiles[:] = [_project(record) for record in self.offer(seeds)]
        except Exception:
            found = None
        finally:
            with self._lock:
                self._pending.discard((title, series))
                if found is None:
                    self._silent[(title, series)] = self.clock() + SILENT

    def _latin_of(self, name: str) -> str:
        """Латиница родни из паспорта - под русским языком показ на неё не смотрит.

        Не звать паспорт впустую (:func:`torrcast.domain.spoken_title.spoken_title`
        под русским отвечает записью в любом случае) - Wikipedia не спрашивают ради
        ответа, который никто не прочитает.
        """
        return self.passport(name, False, TIMEOUT).title if tongue() == EN else ""
