"""Зеркало превью поиска (TC-1126): список растёт, пока фоновый круг ещё не вернулся."""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Any, cast

import pytest

import hass.search_progress as module
from hass.catalog_tiles import CatalogTiles
from hass.hit_posters import HitPosters
from hass.poster_shelf import PosterShelf
from hass.refused_error import RefusedError
from hass.search_job import SearchJob
from hass.search_progress import JOB_TTL, search_progress
from tests.fakes import composition
from tests.usecases.discover.world import Indexer, row, wire_catalogue
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from torrcast.domain.profile import CAUTIOUS
from torrcast.usecases.discover.search_circle import search_circle

_CONFIG = Config(prowlarr_apikey="KEY")
_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=44),
]
_WE = [
    row("Мы / Us (2019) BDRip 1080p", "a"),
    row("Мы / Us (2019) WEB-DL 720p", "b"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2020) S02 WEB-DL 1080p", "c"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2020) S02 WEB-DL 720p", "d"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2024) S06 WEB-DL 1080p", "e"),
    row("Чем мы заняты в тени / What We Do in the Shadows (2024) S06 WEB-DL 720p", "f"),
]


@pytest.fixture(autouse=True)
def _clear_jobs() -> None:
    """Реестр заходов общий на процесс: тесты не смеют путать чужой запрос со своим."""
    module._jobs.clear()


def _detect(_config: Config) -> Choice:
    return Choice(CAUTIOUS, "тест")


def _remember(*_args: Any, **_kwargs: Any) -> None:
    return None


def _as_is(results: list[JsonValue]) -> list[JsonValue]:
    """Приговор обложек без сети: фоновый круг переживает тест и не смеет звать настоящий."""
    return results


class _PreviewClient(Indexer):
    """Тот же поддельный клиент, только с ``inflight()`` - его и просит превью."""

    def __init__(self, *args: Any, raw: list[Any] | None = None, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._raw = raw or []

    def inflight(self) -> list[Any]:
        return list(self._raw)


def _blocking_search(client: _PreviewClient, gate: threading.Event) -> Any:
    """Круг поиска, который отдаёт клиента сразу и не возвращается, пока не отпустят."""

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        on_indexer(client)
        gate.wait(2.0)
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    return search


def _poll(text: str, search: Any) -> tuple[list[Any], bool]:
    return search_progress(_CONFIG, text, _detect, _remember, search=search, offer=_as_is)


def test_a_still_running_job_answers_with_a_preview_before_the_circle_returns() -> None:
    """🔴 Ядро карточки: находка первого ответившего видна ДО конца круга."""
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)
    try:
        results, partial = _poll("тачки", search)
        deadline = time.monotonic() + 1.0
        while not results and time.monotonic() < deadline:
            results, partial = _poll("тачки", search)

        assert partial is True, "круг ещё держит клиент за шлагбаумом"
        assert [hit["title"] for hit in results] == ["Тачки", "Тачки 2"]
        assert all(hit["default"] is False for hit in results), (
            "превью не решает за отбор, кто взят по умолчанию (TC-1126)"
        )
    finally:
        gate.set()


def test_a_preview_keeps_a_crowded_short_name_the_map_proves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 `_peek` обязан разбирать «Мы» тем же правилом, что и первый круг."""
    wire_catalogue()
    known = {
        "мы": [MapPicture("Мы", 2019, False, "Us", 399488)],
        "чем-мы-заняты-в-тени": [
            MapPicture("Чем мы заняты в тени", 2019, True, "What We Do in the Shadows", 129020)
        ],
    }
    composition.use_known_pictures(monkeypatch, lambda title: known.get(title.casefold(), []))
    job = SearchJob(client=_PreviewClient(raw=_WE))

    hits = [hit for hit in module._peek("Мы", job) if isinstance(hit, dict)]
    assert [hit["title"] for hit in hits] == ["Мы"]


def test_a_still_running_preview_carries_the_poster_verdict() -> None:
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)

    def offer(results: list[JsonValue]) -> list[JsonValue]:
        return [
            {**hit, "poster": "p-" + str(hit["key"])} if isinstance(hit, dict) else hit
            for hit in results
        ]

    try:
        results, partial = search_progress(
            _CONFIG, "тачки", _detect, _remember, search=search, offer=offer
        )
        deadline = time.monotonic() + 1.0
        dressed = [isinstance(hit, dict) and hit.get("poster") for hit in results]
        while not (dressed and all(dressed)) and time.monotonic() < deadline:
            results, partial = search_progress(
                _CONFIG, "тачки", _detect, _remember, search=search, offer=offer
            )
            dressed = [isinstance(hit, dict) and hit.get("poster") for hit in results]

        assert partial is True
        assert results
        hits = [hit for hit in results if isinstance(hit, dict)]
        assert [hit.get("poster") for hit in hits] == ["p-" + str(hit.get("key")) for hit in hits]
    finally:
        gate.set()


def test_a_slow_poster_verdict_does_not_hold_the_preview_poll() -> None:
    """🔴 Опрос превью ждал приговор обложек (до 8 с): обложка доезжает следующим опросом."""
    wire_catalogue()
    gate, verdict = threading.Event(), threading.Event()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)

    def offer(results: list[JsonValue]) -> list[JsonValue]:
        verdict.wait(2.0)
        return [{**hit, "poster": "p"} if isinstance(hit, dict) else hit for hit in results]

    def poll() -> tuple[list[JsonValue], bool]:
        return search_progress(_CONFIG, "тачки", _detect, _remember, search=search, offer=offer)

    try:
        results: list[JsonValue] = []
        deadline = time.monotonic() + 1.0
        while not results and time.monotonic() < deadline:
            results, _partial = poll()
        started = time.monotonic()
        results, _partial = poll()

        assert time.monotonic() - started < 0.5
        assert [hit.get("poster") for hit in results if isinstance(hit, dict)] == [None, None]
        verdict.set()
        while time.monotonic() < deadline + 1.0 and not all(
            isinstance(hit, dict) and hit.get("poster") for hit in results
        ):  # results is non-empty here: the loop above filled it
            results, _partial = poll()
        assert [hit.get("poster") for hit in results if isinstance(hit, dict)] == ["p", "p"]
    finally:
        verdict.set()
        gate.set()


def test_a_finished_circle_shows_its_list_while_the_poster_verdict_still_runs() -> None:
    """🔴 Готовый круг ждал приговор обложек (1.1-1.6 с на стенде), и плиток не было вовсе."""
    wire_catalogue()
    verdict = threading.Event()
    client = Indexer(answers={"тачки": _CARS})

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    def offer(results: list[JsonValue]) -> list[JsonValue]:
        verdict.wait(2.0)
        return [{**hit, "poster": "p"} if isinstance(hit, dict) else hit for hit in results]

    def poll() -> tuple[list[Any], bool]:
        return search_progress(_CONFIG, "тачки", _detect, _remember, search=search, offer=offer)

    try:
        results, partial = poll()
        deadline = time.monotonic() + 1.0
        while not results and time.monotonic() < deadline:
            results, partial = poll()
        assert partial is True
        assert [(hit["title"], hit.get("poster")) for hit in results] == [
            ("Тачки", None),
            ("Тачки 2", None),
        ]
        verdict.set()
        while partial and time.monotonic() < deadline + 2.0:
            results, partial = poll()
        assert [hit.get("poster") for hit in results] == ["p", "p"]
    finally:
        verdict.set()


def test_the_final_poll_carries_the_real_default_and_partial_false() -> None:
    wire_catalogue()
    gate = threading.Event()
    gate.set()  # круг возвращается сразу же
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)

    results, partial = _poll("тачки", search)
    deadline = time.monotonic() + 1.0
    while partial and time.monotonic() < deadline:
        results, partial = _poll("тачки", search)

    assert partial is False
    assert len(results) == 2
    assert sum(1 for hit in results if hit["default"]) == 1


def test_the_final_list_goes_through_the_same_poster_verdict_as_plain_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Веб-выдача шла без обложек: итог не проходил приговор, который проходит HA."""
    wire_catalogue()
    gate = threading.Event()
    gate.set()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    search = _blocking_search(client, gate)
    monkeypatch.setattr(
        "hass.searching.OFFER",
        lambda results: [{**hit, "poster": "p-" + hit["key"]} for hit in results],
    )

    def poll() -> tuple[list[Any], bool]:
        return search_progress(_CONFIG, "тачки", _detect, _remember, search=search)

    results, partial = poll()
    deadline = time.monotonic() + 1.0
    while partial and time.monotonic() < deadline:
        results, partial = poll()

    assert partial is False
    assert [hit["poster"] for hit in results] == ["p-" + hit["key"] for hit in results]
    assert len(results) == 2


def test_a_second_poll_of_the_same_query_does_not_start_a_second_search() -> None:
    wire_catalogue()
    gate = threading.Event()
    gate.set()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)
    calls: list[int] = []

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        calls.append(1)
        on_indexer(client)
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    _results, partial = _poll("тачки", search)
    deadline = time.monotonic() + 1.0
    while partial and time.monotonic() < deadline:
        _results, partial = _poll("тачки", search)
    _poll("тачки", search)
    _poll("тачки", search)

    assert len(calls) == 1, "тот же запрос второй раз индексеров не тревожит"


def test_a_new_job_after_the_ttl_keeps_the_poster_verdict_already_known(tmp_path: Path) -> None:
    """Повторный поиск берёт готовую обложку с полки, не судит её второй раз."""
    wire_catalogue()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=_CARS)

    class Posters:
        def __init__(self) -> None:
            self.judged: list[list[Any]] = []

        def wanted(self, asks: Any, _timeout: float) -> dict[Any, list[str]]:
            self.judged.append(list(asks))
            return {ask: [ask.title] for ask in asks}

        def bodies(self, wanted: Any, _timeout: float) -> dict[Any, bytes]:
            return dict.fromkeys(wanted, b"poster")

    source = Posters()
    posters = HitPosters(source=source, shelf=PosterShelf(home=lambda: tmp_path))

    circles: list[str] = []

    def search(config: Config, args: Any, said: Any, profile: Any, on_indexer: Any) -> Any:
        circles.append(args.title_query)
        on_indexer(client)
        return search_circle(
            config,
            args,
            said,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    def finish() -> list[Any]:
        results, partial = search_progress(
            _CONFIG, "тачки", _detect, _remember, search=search, offer=posters.offer
        )
        deadline = time.monotonic() + 2.0
        while partial and time.monotonic() < deadline:
            results, partial = search_progress(
                _CONFIG, "тачки", _detect, _remember, search=search, offer=posters.offer
            )
        assert partial is False
        return results

    first = finish()
    assert any(hit.get("poster") for hit in first)
    assert len(source.judged) == 1
    module._jobs["тачки"].finished_at -= JOB_TTL + 1.0
    second = finish()
    assert len(circles) == 2, "после TTL новый заход не начался: повтор ничего не проверил"
    assert any(hit.get("poster") for hit in second)
    assert len(source.judged) == 1, "повтор после TTL снова судил уже известные обложки"


def test_a_refusal_surfaces_only_once_the_job_is_done() -> None:
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={}, raw=[])
    search = _blocking_search(client, gate)

    results, partial = _poll("нетакого", search)
    assert (results, partial) == ([], True), "отказ ещё не готов - это просто пустой ход"

    gate.set()
    deadline = time.monotonic() + 1.0
    refused: RefusedError | None = None
    while time.monotonic() < deadline:
        try:
            _poll("нетакого", search)
        except RefusedError as caught:
            refused = caught
            break
    assert refused is not None and "нетакого" in refused.word


class _Index:
    """Указатель каталога без выгрузок: одна картина на любой запрос."""

    def __init__(self, *rows: tuple[str, str, str, str, str]) -> None:
        self.rows = list(rows)

    def look(self, _query: str) -> list[tuple[str, str, str, str, str]]:
        return self.rows

    def by_id(self, _tconst: str) -> None:
        return None

    def votes(self) -> dict[str, int]:
        return {}


def _fields(results: list[Any], *names: str) -> list[tuple[Any, ...]]:
    return [tuple(hit.get(name) for name in names) for hit in results]


def _catalog(*rows: tuple[str, str, str, str, str]) -> Any:
    return lambda query: CatalogTiles(query, cast("Any", _Index(*rows)), lambda _q: [])


def test_catalog_tiles_stand_before_the_first_release_and_catch_their_releases() -> None:
    """Картина каталога на экране до раздач; её находка садится в ту же плитку."""
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={"тачки": _CARS}, raw=[])
    search = _blocking_search(client, gate)
    catalog = _catalog(("tt1", "movie", "Cars", "2006", "Тачки"))
    try:
        results, partial = search_progress(
            _CONFIG, "тачки", _detect, _remember, search=search, offer=_as_is, catalog=catalog
        )
        assert partial is True
        assert _fields(results, "title", "pending") == [("Тачки", True)]
    finally:
        gate.set()
    deadline = time.monotonic() + 2.0
    while partial and time.monotonic() < deadline:
        results, partial = search_progress(
            _CONFIG, "тачки", _detect, _remember, search=search, offer=_as_is, catalog=catalog
        )
    assert partial is False
    assert _fields(results, "title", "slot", "dim") == [
        ("Тачки", "movie:тачки:2006", None),
        ("Тачки 2", None, None),
    ]


def test_catalog_tiles_without_releases_dim_only_after_the_whole_circle() -> None:
    """Запрос без раздач: плитки видны, пока круг идёт, и гаснут после него, а не 409."""
    wire_catalogue()
    gate = threading.Event()
    client = _PreviewClient(answers={}, raw=[])
    search = _blocking_search(client, gate)
    catalog = _catalog(("tt2", "movie", "Nope", "2001", "Нетакого"))

    def poll() -> tuple[list[Any], bool]:
        return search_progress(
            _CONFIG, "нетакого", _detect, _remember, search=search, offer=_as_is, catalog=catalog
        )

    results, partial = poll()
    assert partial is True
    assert [(hit["title"], hit.get("pending"), hit.get("dim")) for hit in results] == [
        ("Нетакого", True, None)
    ], "до конца круга плитка ждёт раздачи, а не гаснет"
    gate.set()
    deadline = time.monotonic() + 2.0
    while partial and time.monotonic() < deadline:
        results, partial = poll()
    assert partial is False
    assert [(hit["title"], hit.get("dim")) for hit in results] == [("Нетакого", True)]
