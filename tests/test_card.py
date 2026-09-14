"""Карточка одной картины: собранное тело и заголовок недоехавшей части."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, replace
from typing import Any

import pytest

import web.card as card_page
from tests.fakes.state_store import FakeStateStore
from tests.usecases.rank.releases import media, track
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.facts.fact import Fact
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.select.plan import Plan
from web.answer import JSON
from web.card import WAIT, card
from web.episode_lookup import GRACE
from web.heard import Heard
from web.request import Request
from web.warm_cache import WarmCache

_MOVIE = Picture(title="Interstellar", year=2014, kind="movie", original="Interstellar")
_LEAD = Release(
    raw_name="Interstellar 2014 BDRip 1080p LostFilm",
    title="Interstellar",
    quality="1080p",
    seeders=100,
)
_OTHER = Release(
    raw_name="Interstellar 2014 BDRip 720p AlexFilm",
    title="Interstellar",
    quality="720p",
    seeders=50,
)
_MOVIE.releases = [_LEAD, _OTHER]
_MOVIE_PLAN = Plan(
    picture=_MOVIE, ranked=[_LEAD], runtime=8520.0, warn_mbit=12.0, runtime_estimated=False
)

_SHOW = Picture(title="Show", year=2022, kind="tv")
_SHOW_RELEASE = Release(
    raw_name="Show s01 WEB-DL 1080p LostFilm",
    title="Show",
    quality="1080p",
    seeders=40,
    seasons=(1, 2),
)
_SHOW.releases = [_SHOW_RELEASE]
_SHOW_PLAN = Plan(picture=_SHOW, ranked=[_SHOW_RELEASE], runtime=1500.0, warn_mbit=12.0)


def _plans(plans: list[Plan]) -> Any:
    def _search(*_a: object, **_k: object) -> list[Plan]:
        return plans

    return _search


@dataclass
class _StubEpisodes:
    """Подмена :class:`web.episode_lookup.EpisodeLookup` - тест сам решает, что готово.

    ``None`` изображает разбор, который ещё не успел фон (см. тесты недоехавшей карточки
    в :mod:`web.card`); список - раздачу, которую уже разобрал :meth:`_build`.
    """

    result: list[list[int]] | None

    def table(self, _release: Release, _base_url: str) -> list[list[int]] | None:
        return self.result


@dataclass
class _StubVoices:
    """Подмена :class:`web.voice_lookup.VoiceLookup`: дорожки уже прочитаны или ещё в пути."""

    heard: Heard | None = None
    coming: bool = False
    asked: list[str] = field(default_factory=list)
    live: list[Entry | None] = field(default_factory=list)

    def of(
        self, _plan: Plan, query: str, _config: object, live: Entry | None = None
    ) -> tuple[Heard | None, bool]:
        self.asked.append(query)
        self.live.append(live)
        return self.heard, self.coming


@dataclass
class _StubRelated:
    """Подмена :class:`web.related_lookup.RelatedLookup` - тест сам решает, что готово.

    ``None`` изображает Wikidata, которая ещё не успела фон; список - родню, которую
    :meth:`_build` уже сложил в кэш (пустой список - франшизы нет, это законченный ответ).
    """

    result: list[Any] | None = None
    #: ``None`` при идущем походе - недоезд; без похода - молчание источника.
    pending: bool = True

    def of(self, _title: str, _series: bool) -> list[Any] | None:
        return self.result

    def retry(self, title: str, series: bool) -> list[Any] | None:
        return self.of(title, series)

    def waiting(self, _title: str, _series: bool) -> bool:
        return self.result is None and self.pending


@dataclass
class _RememberingRelated(_StubRelated):
    asked: list[tuple[str, bool]] = field(default_factory=list)

    def of(self, title: str, series: bool) -> list[Any] | None:
        self.asked.append((title, series))
        return self.result


@dataclass
class _StubPoster:
    """Подмена :class:`web.card_poster.CardPoster`: приговор уже вынесен, в сеть не ходим."""

    name: str | None = None

    def of(self, _picture: Picture) -> tuple[str | None, bool]:
        return self.name, False


def _warm(circle: Any) -> WarmCache:
    """Свой прогрев на каждую пробу: согретое соседкой не должно доставаться этой."""
    return WarmCache(circle=circle, blurbs=lambda _pictures: None, spawn=lambda _job: None)


def _wired(
    monkeypatch: pytest.MonkeyPatch,
    plans: list[Plan],
    episodes: list[list[int]] | None = None,
    related: list[Any] | None = None,
    poster: str | None = None,
    voices: _StubVoices | None = None,
) -> None:
    monkeypatch.setattr("web.card.load_config", lambda: Config())
    monkeypatch.setattr("web.card._voices", voices or _StubVoices())
    monkeypatch.setattr("web.card.WARM", _warm(_plans(plans)))
    monkeypatch.setattr("web.card._episodes", _StubEpisodes(episodes))
    monkeypatch.setattr("web.card._related", _StubRelated(related))
    monkeypatch.setattr("web.card._poster", _StubPoster(poster))


def _asked(
    key: str,
    query: str = "interstellar",
    wait: bool = False,
    extra_query: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any], tuple[str, ...]]:
    asked = {"query": query, "wait": "1"} if wait else {"query": query}
    if extra_query:
        asked.update(extra_query)
    answer = card(Request("GET", f"/api/card/{key}", asked, {}))
    assert answer.kind == JSON
    body: dict[str, Any] = json.loads(answer.body)
    return answer.code, body, tuple(name for name, _ in answer.extra)


def test_no_query_is_refused_before_any_search_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> list[Plan]:
        raise AssertionError("поиск не должен звать при пустом query")

    _wired(monkeypatch, [])
    monkeypatch.setattr("web.card.WARM", _warm(_boom))

    answer = card(Request("GET", f"/api/card/{_MOVIE.key}", {}, {}))

    assert answer.code == 400
    assert json.loads(answer.body) == {"error": "no_query"}


def test_a_shelf_card_answers_its_ready_facts_without_waiting_for_the_circle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Клик видимой полки не стоит за одним рабочим поиска раздач."""
    cache = _warm(_plans([_MOVIE_PLAN]))
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    monkeypatch.setattr("web.card.WARM", cache)
    monkeypatch.setattr("web.preview.MenuFacts", lambda *a, **k: _ReadyFacts())
    state_slot.install(FakeStateStore())

    code, body, extra = _asked(
        _MOVIE.key,
        extra_query={
            "title": "Interstellar",
            "shown": "Interstellar",
            "year": "2014",
            "kind": "movie",
        },
    )

    assert code == 200
    assert body["blurb"] == "Сюжет"
    assert body["related"] == []
    assert body["searching"] is True
    assert "X-Torrcast-Partial" in extra
    assert cache.ready("interstellar") is None


def test_an_open_card_starts_its_related_shelf_outside_the_seen_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The opened tile must not depend on its position in the background screen."""
    related = _RememberingRelated([])
    _wired(monkeypatch, [_MOVIE_PLAN])
    monkeypatch.setattr("web.card._related", related)
    state_slot.install(FakeStateStore())

    _asked(
        _MOVIE.key,
        extra_query={"title": "Interstellar", "year": "2014", "kind": "movie"},
    )

    assert related.asked[0] == ("Interstellar", False)


def test_a_full_card_keeps_the_tile_identity_for_its_related_shelf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Нормализация названия кругом не вправе сменить уже показанную полку франшизы."""
    related = _RememberingRelated([])
    _wired(monkeypatch, [_MOVIE_PLAN])
    monkeypatch.setattr("web.card._related", related)
    monkeypatch.setattr("web.card.preview", lambda *_args: None)
    monkeypatch.setattr(
        "web.card._facts", type("_Facts", (), {"of": lambda *_args: _ReadyFacts()})()
    )
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())
    state_slot.install(FakeStateStore())

    _asked(
        _MOVIE.key,
        extra_query={"title": "Tile name", "year": "2000", "kind": "movie"},
    )

    assert related.asked == [("Tile name", False)]


def test_an_unknown_key_is_a_404_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    _wired(monkeypatch, [_MOVIE_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:nobody:1900")

    assert code == 404
    assert body == {"error": "not_found"}


def test_a_search_refusal_surfaces_as_409_with_the_products_own_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refused(*_a: object, **_k: object) -> list[Plan]:
        raise TorrcastError("nothing_found")

    _wired(monkeypatch, [])
    monkeypatch.setattr("web.card.WARM", _warm(_refused))

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 409
    assert body["error"] == "nothing_found"


def test_a_movie_card_lists_every_track_of_the_release_the_show_would_play(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Дефект владельца 14-09-2026: студии из имён раздач не знали английской дорожки."""
    tracks = (track(0, "rus", "MVO (LostFilm)"), track(1, "eng", "Original"), track(2, "jpn", None))
    voices = _StubVoices(Heard(media(tracks=tracks), native=False, studios=()))
    _wired(monkeypatch, [_MOVIE_PLAN], voices=voices)
    state_slot.install(FakeStateStore())

    code, body, extra = _asked(_MOVIE.key, extra_query={"lang": "ru"})

    assert code == 200
    assert body["title"] == "Interstellar"
    assert body["kind"] == "movie"
    assert body["runtime"] == 8520.0
    assert body["runtime_estimated"] is False
    assert body["seasons"] == []
    assert [voice["label"] for voice in body["voices"]] == [
        "русский · MVO (LostFilm)",
        "английский · Original",
        "японский",
    ]
    assert [voice["name"] for voice in body["voices"]] == ["LostFilm", "eng", "jpn"]
    assert voices.asked == ["interstellar"]
    assert body["releases_count"] == 2
    assert body["playing"] is False
    assert "X-Torrcast-Partial" not in extra


def test_the_card_names_its_picture_and_release_by_keys_for_the_play_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Играть» зовёт показ ключами карточки: номер в выдаче гуляет от круга к кругу."""
    heard = Heard(media(tracks=(track(0, "eng", None),)), False, (), release="c" * 40)
    _wired(monkeypatch, [_MOVIE_PLAN], voices=_StubVoices(heard))
    state_slot.install(FakeStateStore())

    _code, body, _extra = _asked(_MOVIE.key)

    assert body["picture"] == _MOVIE_PLAN.picture.key
    assert body["release"] == "c" * 40


def test_tracks_still_being_read_do_not_hold_the_waiting_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Отбор дорожек держал долгий ответ до потолка: «Играть» у «Тачек» 15.6 с."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[], voices=_StubVoices(coming=True))
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())
    monkeypatch.setattr("web.card.WAIT", 30.0)
    monkeypatch.setattr("web.card._TICK", 0.01)
    state_slot.install(FakeStateStore())
    began = time.monotonic()

    _code, body, extra = _asked(_MOVIE.key, wait=True)

    assert time.monotonic() - began < 5.0
    assert body["voices"] == []
    assert body["voices_pending"] is True
    assert "X-Torrcast-Partial" not in extra


@dataclass
class _LateVoices:
    """Дорожки, прочитанные на ``after``-м взгляде долгого ответа."""

    after: int
    looks: int = 0

    def of(
        self, _plan: Plan, _query: str, _base_url: str, _live: object
    ) -> tuple[Heard | None, bool]:
        self.looks += 1
        if self.looks < self.after:
            return None, True
        return Heard(media(tracks=(track(0, "eng", None),)), native=False, studios=()), False


def test_a_voices_ask_holds_the_answer_until_the_tracks_arrive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    late = _LateVoices(after=3)
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    monkeypatch.setattr("web.card._voices", late)
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())
    monkeypatch.setattr("web.card._TICK", 0.0)
    state_slot.install(FakeStateStore())

    _code, body, _extra = _asked(_MOVIE.key, wait=True, extra_query={"voices": "1"})

    assert [voice["name"] for voice in body["voices"]] == ["eng"]
    assert body["voices_pending"] is False
    assert late.looks == 3


def test_a_picture_showing_on_the_receiver_right_now_marks_the_card_playing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-1225: карточка играющей картины помнит об этом - кнопки решают по этому полю."""
    _wired(monkeypatch, [_MOVIE_PLAN])
    fake = FakeStateStore()
    state = fake.load()
    state.entries[_MOVIE.key] = Entry(
        "Interstellar", "magnet:interstellar", kind="movie", pos=120.0, dur=8520.0, torrent="abc"
    )
    fake.save(state)
    state_slot.install(fake)

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 200
    assert body["playing"] is True


@pytest.mark.parametrize(("tv", "offered"), [("", False), ("192.168.1.90", True)])
def test_the_card_offers_the_tv_only_on_a_machine_that_has_one(
    monkeypatch: pytest.MonkeyPatch, tv: str, offered: bool
) -> None:
    """Без ТВ в настройке карточка не зовёт «На ТВ»: кнопку по этому полю не рисуют."""
    _wired(monkeypatch, [_MOVIE_PLAN])
    monkeypatch.setattr("web.card.load_config", lambda: Config(tv=tv))
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 200
    assert body["tv"] is offered


def test_a_bookmark_without_a_live_receiver_does_not_claim_the_card_is_playing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Закладка сама по себе не значит «играет» - показ мог давно кончиться (TC-1225)."""
    _wired(monkeypatch, [_MOVIE_PLAN])
    fake = FakeStateStore()
    state = fake.load()
    state.entries[_MOVIE.key] = Entry(
        "Interstellar", "magnet:interstellar", kind="movie", pos=120.0, dur=8520.0
    )
    fake.save(state)
    state_slot.install(fake)

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 200
    assert body["playing"] is False


def test_the_rating_leaves_as_a_number_because_the_page_says_the_source_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Справка держит рейтинг строкой с источником; наружу едет число, слово - каталогом."""
    _wired(monkeypatch, [_MOVIE_PLAN])
    state_slot.install(FakeStateStore())
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())

    _code, body, _extra = _asked(_MOVIE.key)

    assert body["rating"] == 8.5


def test_a_cached_missing_article_finishes_the_related_shelf_without_a_circle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_MOVIE_PLAN])
    state_slot.install(FakeStateStore())
    monkeypatch.setenv("TORRCAST_STATE", "/nonexistent-so-facts-cache-stays-empty")

    _code, body, extra = _asked(_MOVIE.key)

    assert body["blurb"] == ""
    assert body["rating"] is None
    assert "X-Torrcast-Partial" not in extra


def test_a_picture_the_source_answered_nothing_about_is_not_marked_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Статьи нет - описания не будет никогда, и переспрашивать карточку незачем.

    Замер 10-09-2026 на стенде `.104`: у `tv:пассажиры-2:2022` (ни статьи, ни родни)
    страница делала шесть ходов в `/api/card` и останавливалась только своим потолком
    в пять доборов, а не потому, что карточка налилась.
    """
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    state_slot.install(FakeStateStore())
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _AnsweredEmptyFacts())

    _code, body, extra = _asked(_MOVIE.key)

    assert body["blurb"] == ""
    assert body["rating"] is None
    assert "X-Torrcast-Partial" not in extra


def test_a_franchise_the_source_went_silent_on_does_not_hold_the_card_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Родня без идущего похода - молчание источника: у картины без статьи её не будет,
    а карточка висела недоехавшей, и страница спрашивала её пять раз (стенд `.104`,
    11-09-2026: четыре фильма полки из пяти)."""
    _wired(monkeypatch, [_MOVIE_PLAN])
    monkeypatch.setattr("web.card._related", _StubRelated(None, pending=False))
    state_slot.install(FakeStateStore())
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _AnsweredEmptyFacts())

    _code, body, extra = _asked(_MOVIE.key)

    assert body["related"] is None
    assert "X-Torrcast-Partial" not in extra


def test_a_series_without_a_bookmark_only_counts_seasons_from_release_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_SHOW_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked(_SHOW.key, query="show")

    assert code == 200
    assert body["seasons"] == [{"n": 1, "episodes": []}, {"n": 2, "episodes": []}]
    assert body["resumable"] is False
    assert body["label"] == ""


def test_a_series_with_a_bookmark_marks_earlier_episodes_watched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_SHOW_PLAN])
    fake = FakeStateStore()
    state = fake.load()
    state.entries[_SHOW.key] = Entry(
        "Show",
        "magnet:show",
        kind="tv",
        season=1,
        episode=2,
        pos=30.0,
        dur=1200.0,
        episodes=[[1, 1, 0, 0], [1, 2, 1, 0]],
    )
    fake.save(state)
    state_slot.install(fake)

    code, body, _extra = _asked(_SHOW.key, query="show")

    assert code == 200
    assert body["label"] == "s1e2"
    assert body["resumable"] is True
    season_one = next(season for season in body["seasons"] if season["n"] == 1)
    by_episode = {episode["n"]: episode for episode in season_one["episodes"]}
    assert by_episode[1]["watched"] is True
    assert by_episode[1]["pos"] == 0.0
    assert by_episode[2]["watched"] is False
    assert by_episode[2]["pos"] == 30.0


def test_a_never_opened_series_shows_episodes_once_the_release_is_parsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сериал, которого никогда не открывали, - нет закладки, но раздача уже разобрана.

    Это и есть цель TC-1115: без единого показа карточка обязана назвать номера серий,
    а не только счётчик сезонов из имён раздач.
    """
    _wired(monkeypatch, [_SHOW_PLAN], episodes=[[1, 1, 0, 0], [1, 2, 1, 0], [2, 1, 2, 0]])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked(_SHOW.key, query="show")

    assert code == 200
    assert body["resumable"] is False
    seasons = {season["n"]: season for season in body["seasons"]}
    assert {episode["n"] for episode in seasons[1]["episodes"]} == {1, 2}
    assert {episode["n"] for episode in seasons[2]["episodes"]} == {1}
    assert all(episode["watched"] is False for episode in seasons[1]["episodes"])


def test_a_series_names_the_release_whose_files_list_its_episodes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Строка серии должна передать показу hash своей файловой таблицы, не дорожек."""
    release = replace(_SHOW_RELEASE, magnet="magnet:?xt=urn:btih:" + "a" * 40)
    picture = Picture(title="Show", year=2022, kind="tv", releases=[release])
    plan = Plan(picture=picture, ranked=[release], runtime=1500.0, warn_mbit=12.0)
    heard = Heard(media(tracks=(track(0, "rus", None),)), False, (), release="b" * 40)
    _wired(monkeypatch, [plan], episodes=[[1, 1]], voices=_StubVoices(heard))
    state_slot.install(FakeStateStore())

    _code, body, _extra = _asked(picture.key, query="show")

    assert body["release"] == "a" * 40


def test_a_never_opened_series_is_marked_partial_while_the_release_still_parses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Разбор ещё не готов - заголовок недоехавшей части, а не тихая пустота навсегда."""
    _wired(monkeypatch, [_SHOW_PLAN], episodes=None)
    state_slot.install(FakeStateStore())

    _code, body, extra = _asked(_SHOW.key, query="show")

    assert body["seasons"] == [{"n": 1, "episodes": []}, {"n": 2, "episodes": []}]
    assert "X-Torrcast-Partial" in extra


def test_a_franchise_picture_shows_the_related_tiles_wikidata_already_answered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Родня франшизы (§8) едет плиткой той же формы, что и полки, а не заглушкой."""
    tile = {
        "key": "movie:гарри-поттер-и-тайная-комната:2002",
        "title": "Гарри Поттер и Тайная комната",
        "year": 2002,
        "kind": "movie",
        "quality": None,
        "poster": "abc123",
        "query": "Гарри Поттер и Тайная комната",
    }
    _wired(monkeypatch, [_MOVIE_PLAN], related=[tile])
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 200
    assert body["related"] == [tile]


def test_a_franchise_still_unanswered_by_wikidata_is_marked_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Wikidata ещё не ответила - заголовок недоехавшей части, а не молчаливая пустота."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=None)
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())
    state_slot.install(FakeStateStore())

    _code, body, extra = _asked(_MOVIE.key)

    assert body["related"] is None
    assert "X-Torrcast-Partial" in extra


def test_the_open_picture_is_never_a_tile_in_its_own_franchise_shelf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Полка родни - ДРУГИЕ части франшизы (§8), и плитки на саму себя в ней нет.

    Голое имя серии паспорт отдаёт статьёй франшизы, и родня приезжает вместе с первой
    картиной: замер 10-09-2026 на стенде `.104` - под `movie:джон-уик:2014` пятой
    плиткой стоял «Джон Уик» 2014 года, ведущий на эту же страницу.
    """
    mine = {"key": _MOVIE.key, "title": "Interstellar", "year": 2014, "kind": "movie"}
    other = {"key": "movie:tenet:2020", "title": "Tenet", "year": 2020, "kind": "movie"}
    _wired(monkeypatch, [_MOVIE_PLAN], related=[mine, other])
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _ReadyFacts())
    state_slot.install(FakeStateStore())

    _code, body, _extra = _asked(_MOVIE.key)

    assert body["related"] == [other], "картина стоит плиткой в собственной полке родни"


def test_a_picture_with_no_franchise_shows_an_empty_related_shelf_not_a_pending_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Франшизы нет - это законченный ответ (пустая полка), а не «ещё не готово»."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    state_slot.install(FakeStateStore())
    monkeypatch.setattr(
        "web.card.MenuFacts",
        lambda *a, **k: _ReadyFacts(),
    )

    code, body, extra = _asked(_MOVIE.key)

    assert code == 200
    assert body["related"] == []
    assert "X-Torrcast-Partial" not in extra


class _ReadyFacts:
    """Справка, которая никогда не заставляет карточку ждать сеть - для теста ниже."""

    def start(self) -> None:
        return None

    def ready(self, _title: str, _year: int | None) -> Any:
        return _Fact()

    def answered(self, _title: str, _year: int | None) -> bool:
        return True


class _AnsweredEmptyFacts:
    """Источник ОТВЕТИЛ, и сказать ему нечего: справка пустая, но законченная."""

    def start(self) -> None:
        return None

    def ready(self, _title: str, _year: int | None) -> Any:
        return Fact()

    def answered(self, _title: str, _year: int | None) -> bool:
        return True


@dataclass
class _Fact:
    rating: str = "IMDb 8.5"
    about: str = "Сюжет"


_RUSSIAN = Picture(title="Целиком и полностью", year=2022, kind="movie", original="Bones and All")
_RUSSIAN_RELEASE = Release(
    raw_name="Bones and All 2022 BDRip 1080p", title="Bones and All", quality="1080p", seeders=20
)
_RUSSIAN.releases = [_RUSSIAN_RELEASE]
_RUSSIAN_PLAN = Plan(picture=_RUSSIAN, ranked=[_RUSSIAN_RELEASE], runtime=7980.0, warn_mbit=12.0)

_NAMESAKE = Picture(
    title="Энтони Джесельник: Целиком и полностью",
    year=2024,
    kind="movie",
    original="Anthony Jeselnik: Bones and All",
)
_NAMESAKE.releases = [_RUSSIAN_RELEASE]
_NAMESAKE_PLAN = Plan(picture=_NAMESAKE, ranked=[_RUSSIAN_RELEASE], runtime=3600.0, warn_mbit=12.0)


def test_a_shelf_key_named_in_the_original_opens_the_same_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Плитка полки зовёт картину именем раздачи, круг - прокатным: ключи расходятся.

    До этого всякая плитка «Новинок» и «Популярного» открывала пустую карточку: ключ
    ленты не совпадал ни с одним ключом круга, и ответом был 404 (замер на стенде
    `.104` 07-09-2026).
    """
    _wired(monkeypatch, [_RUSSIAN_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:bones-and-all:2022", query="Bones and All")

    assert code == 200
    assert body["title"] == "Целиком и полностью"
    assert body["original"] == "Bones and All"


def test_the_shown_name_speaks_the_original_under_english(
    monkeypatch: pytest.MonkeyPatch, _english: None
) -> None:
    """§8: карточка говорит найденной латиницей, а запись остаётся розыскной, под английским."""
    _wired(monkeypatch, [_RUSSIAN_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:bones-and-all:2022", query="Bones and All")

    assert code == 200
    assert body["title"] == "Целиком и полностью"
    assert body["shown"] == "Bones and All"


def test_the_shown_name_stays_recorded_under_russian_even_with_an_original(
    monkeypatch: pytest.MonkeyPatch, _russian_product: None
) -> None:
    """Позитивный контроль: под русским языком найденная латиница ничего не меняет."""
    _wired(monkeypatch, [_RUSSIAN_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:bones-and-all:2022", query="Bones and All")

    assert code == 200
    assert body["title"] == "Целиком и полностью"
    assert body["shown"] == "Целиком и полностью"


def test_a_namesake_in_another_year_is_not_taken_for_the_asked_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Второй ключ собран правилом :attr:`Picture.key`, а не поиском имени в строке."""
    _wired(monkeypatch, [_NAMESAKE_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:bones-and-all:2022", query="Bones and All")

    assert code == 404
    assert body == {"error": "not_found"}


def test_the_card_carries_its_own_number_in_the_circle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Номер картины в круге - то, чем «Играть» просит показ ИМЕННО ЭТУ картину.

    Без него показ брал бы главную по запросу, и карточка второй находки запускала
    первую (ТЗ §4.3).
    """
    _wired(monkeypatch, [_NAMESAKE_PLAN, _RUSSIAN_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:bones-and-all:2022", query="Bones and All")

    assert code == 200
    assert body["pick"] == 2


def test_the_card_names_its_poster_by_the_same_verdict_the_tiles_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Имя без приговора вело на 404: карточка «Usuzumizakura GARO» стояла без обложки."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[], poster="f00d")
    state_slot.install(FakeStateStore())
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _AnsweredEmptyFacts())

    _code, body, extra = _asked(_MOVIE.key)

    assert body["poster"] == "f00d"
    assert "X-Torrcast-Partial" not in extra


def test_a_picture_the_verdict_found_no_art_for_names_no_poster(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Картинки нет - поля нет: страница оставляет обложку плитки, а не битую ссылку."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    state_slot.install(FakeStateStore())
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _AnsweredEmptyFacts())

    _code, body, _extra = _asked(_MOVIE.key)

    assert body["poster"] is None


class _LateFacts:
    """Справка, которая доезжает на третьем взгляде: долгий переспрос обязан её дождаться."""

    def __init__(self, after: int) -> None:
        self.after = after
        self.looks = 0

    def start(self) -> None:
        return None

    def ready(self, _title: str, _year: int | None) -> Any:
        self.looks += 1
        return _Fact() if self.looks >= self.after else Fact()

    def answered(self, _title: str, _year: int | None) -> bool:
        return self.looks >= self.after


def test_a_waiting_ask_holds_the_answer_until_the_blurb_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Короткий опрос бросал страницу со скелетом: долгий держит ответ до описания."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    state_slot.install(FakeStateStore())
    late = _LateFacts(after=3)
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: late)
    monkeypatch.setattr("web.card._TICK", 0.0)

    _code, body, extra = _asked(_MOVIE.key, wait=True)

    assert body["blurb"] == "Сюжет"
    assert "X-Torrcast-Partial" not in extra
    assert late.looks == 3


def test_a_waiting_ask_sees_the_show_that_began_after_its_first_look(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Показ стартует между взглядами: долгий ответ обязан назвать его сразу."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    fake = FakeStateStore()
    state = fake.load()
    state.entries[_MOVIE.key] = Entry("Interstellar", "magnet:interstellar", kind="movie")
    fake.save(state)
    state_slot.install(fake)
    late = _LateFacts(after=3)
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: late)
    original = card_page._body
    looks = 0

    def _body(*args: Any, **kwargs: Any) -> tuple[dict[str, Any], bool]:
        nonlocal looks
        body = original(*args, **kwargs)
        looks += 1
        if looks == 1:
            started = fake.load()
            started.entries[_MOVIE.key] = Entry(
                "Interstellar", "magnet:interstellar", kind="movie", torrent="abc"
            )
            fake.save(started)
        return body

    monkeypatch.setattr("web.card._body", _body)
    monkeypatch.setattr("web.card._TICK", 0.0)

    _code, body, _extra = _asked(_MOVIE.key, wait=True)

    assert body["playing"] is True


def test_a_waiting_ask_gives_up_at_its_ceiling_and_still_says_partial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    state_slot.install(FakeStateStore())
    monkeypatch.setattr("web.card.MenuFacts", lambda *a, **k: _LateFacts(after=10**9))
    monkeypatch.setattr("web.card.WAIT", 0.05)
    monkeypatch.setattr("web.card._TICK", 0.01)

    _code, body, extra = _asked(_MOVIE.key, wait=True)

    assert body["blurb"] is None
    assert "X-Torrcast-Partial" in extra


def test_the_waiting_ask_outlasts_the_first_contact_of_the_episode_lookup() -> None:
    """🔴 Разбор серий заводит первый ``GET``, долгий заход идёт вторым: при равных 8 с
    заход кончался раньше приговора мёртвому рою, и страница спрашивала третий раз."""
    assert WAIT > GRACE


def test_a_waiting_ask_brings_parts_landing_close_together_in_one_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Ответ на первую же перемену стоил странице лишнего запроса: родня и серии
    приехали через 2.1 с, приговор обложки через 2.7 с, и третий ``GET`` не нёс ничего."""
    _wired(monkeypatch, [_MOVIE_PLAN], related=[])
    state_slot.install(FakeStateStore())
    looks = [({"related": None}, True), ({"related": []}, True), ({"related": []}, False)]
    monkeypatch.setattr("web.card._body", lambda *_a: looks.pop(0))
    monkeypatch.setattr("web.card._TICK", 0.0)

    _code, body, extra = _asked(_MOVIE.key, wait=True)

    assert body == {"related": []}
    assert "X-Torrcast-Partial" not in extra
    assert looks == []


def test_a_card_asks_the_tracks_of_its_live_bookmark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Живая закладка идёт в отбор дорожек: «Играть» продолжит её, а не раздачу карточки."""
    voices = _StubVoices()
    _wired(monkeypatch, [_MOVIE_PLAN], related=[], voices=voices)
    saved = FakeStateStore()
    state = saved.load()
    state.put(_MOVIE.key, Entry(title="Interstellar", magnet="magnet:kept", dur=9.0, pos=3.0))
    saved.save(state)
    state_slot.install(saved)

    _asked(_MOVIE.key)

    assert [live.magnet if live else None for live in voices.live] == ["magnet:kept"]
