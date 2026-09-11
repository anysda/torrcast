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
from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify
from torrcast.domain.spoken_title import spoken_title

#: Тот же ``FranchiseKin.of``: имя, серия ли картина, срок сети - родня; ``None`` -
#: сеть промолчала, и это НЕ законченный ответ: в кэш ему нельзя, следующий вопрос
#: заводит новый добор (:meth:`RelatedLookup._build`).
Franchise = Callable[[str, bool, float], list[Kin] | None]
#: Тот же ``Passport.of``: паспорт родни латиницей - Wikidata своего не называет
#: (:func:`_seed`).
PassportOf = Callable[[str, bool, float], Origin]
#: Тот же ``HitPosters.offer``: те же записи, с обложкой у тех, кому она нашлась.
Offer = Callable[[list[JsonValue]], list[JsonValue]]
Spawn = Callable[[Callable[[], None]], None]
TIMEOUT = 8.0
RETRY = 3600.0
#: Сколько молчание источника держит имя от нового похода: ``None`` отдаёт и картина без
#: статьи в Википедии, и без срока каждый тик долгого захода карточки шёл в сеть заново
#: (стенд `.104`, 11-09-2026: четыре фильма полки из пяти, по пять ``GET`` на карточку).
SILENT = 120.0
#: Та же форма, что у плитки полок (:data:`web.shelves_cache._TILE_FIELDS`) - страница
#: рисует обе плитки одним и тем же кодом, а не двумя похожими. ``shown`` - имя ДЛЯ
#: ЧЕЛОВЕКА, ``title`` остаётся записанным ради розыска обложки и ``query``.
_TILE_FIELDS: tuple[str, ...] = (
    "key",
    "title",
    "shown",
    "year",
    "kind",
    "quality",
    "poster",
    "query",
)


def _daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True, name="related-lookup").start()


def _no_passport(_title: str, _series: bool, _timeout: float) -> Origin:
    """Паспорт по умолчанию: без проводки родня остаётся под записанным именем."""
    return Origin()


def _seed(kin: Kin, original: str) -> dict[str, JsonValue]:
    """Плитка родни до обложки: ``original`` в ней только на розыск обложки, не на показ.

    Wikidata не называет род родни - франшизы приёмки (§8) все до одной кино, и это
    умолчание, а не подпорка под конкретное название. Латиница - паспорт того же имени
    (:func:`torrcast.usecases.passport.Passport.of`), каким гейт добора проверяет саму
    картину; нет статьи на другом языке - латиницы у родни тоже нет, и это честно.
    """
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
    offer: Offer = hits.offer
    passport: PassportOf = _no_passport
    spawn: Spawn = _daemon
    clock: Callable[[], float] = time.monotonic
    _tiles: dict[tuple[str, bool], tuple[list[JsonValue], float]] = field(default_factory=dict)
    _pending: set[tuple[str, bool]] = field(default_factory=set)
    _silent: dict[tuple[str, bool], float] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def of(self, title: str, series: bool) -> list[JsonValue] | None:
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
        self.spawn(lambda: self._build(title, series))
        with self._lock:
            cached = self._tiles.get(asked)
            return cached[0] if cached is not None else None

    def waiting(self, title: str, series: bool) -> bool:
        """Идёт ли поход за роднёй: ``None`` без похода - молчание, ждать его нечего."""
        with self._lock:
            return (title, series) in self._pending

    def _build(self, title: str, series: bool) -> None:
        """Собрать плитки родни; молчание в кэш не ложится - переспросят после :data:`SILENT`.

        🔴 Пустая полка кэшируется только когда она ОТВЕЧЕНА (:meth:`FranchiseKin.of`
        отдал список). ``None`` - сеть промолчала, и записать его «родни нет» на час
        (:data:`RETRY`) значило бы гасить полку одной оборванной связью: замер
        10-09-2026 на стенде `.104` - «Чужой» отвечал пустой полкой при шести частях
        франшизы в живом ответе Wikidata. Ошибка добора - тоже не ответ: без
        ``try/finally`` упавший фон держал имя в ``_pending`` вечно, и полка висела
        недоехавшей до перезапуска процесса.
        """
        found: list[Kin] | None = None
        try:
            found = self.franchise(title, series, TIMEOUT)
            if found is None:
                return
            seeds: list[JsonValue] = [_seed(kin, self._latin_of(kin.name)) for kin in found]
            tiles = [_project(record) for record in self.offer(seeds)]
            with self._lock:
                self._tiles[(title, series)] = (tiles, self.clock() + RETRY)
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


__all__ = ["Franchise", "PassportOf", "RelatedLookup", "Spawn"]
