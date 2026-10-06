"""VoiceLookup: отбор раздачи в фоне, кэш на процесс, прогретое убрано за собой."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.fakes.torrent_engines import FakeTorrentEngines
from tests.usecases.rank.releases import media, track
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan
from web.episode_lookup import RETRY
from web.voice_lookup import VoiceLookup

_RELEASE = Release(raw_name="Film 2010 BDRip 1080p LostFilm", title="Film", magnet="magnet:f")
_PICTURE = Picture(title="Film", year=2010, kind="movie", releases=[_RELEASE])
_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE], runtime=0, warn_mbit=0)
_CONFIG = Config(torrserver_url="http://ts", receiver_profile="q70d")
_MEDIA = media(tracks=(track(0, "rus", "Dub"), track(1, "eng", "Original")))


@dataclass
class _Prep:
    found: Any
    release: Release = _RELEASE
    voice_fallback: bool = False


@dataclass
class _Bench:
    """Подмена стенда отбора: отвечает паспортом или отказом и помнит уборку."""

    answer: Any
    dropped: list[bool] = field(default_factory=list)
    kept: list[Any] = field(default_factory=list)
    asked: list[tuple[Plan, Any]] = field(default_factory=list)

    profiles: list[Any] = field(default_factory=list)
    release: Release = _RELEASE
    lends: bool = False

    def __call__(
        self, _engine: object, choose: object = None, profile: Any = None, lends: bool = False
    ) -> _Bench:
        self.profiles.append(profile)
        self.lends = lends
        return self

    def resolve(self, plan: Plan, args: Any, _progress: object) -> _Prep:
        self.asked.append((plan, args))
        if isinstance(self.answer, Exception):
            raise self.answer
        return _Prep(self.answer, self.release)

    def drop_all(self) -> None:
        self.dropped.append(True)

    def keep_only(self, prep: Any) -> None:
        self.kept.append(prep)


@dataclass
class _Clock:
    now: float = 1000.0

    def __call__(self) -> float:
        return self.now


def _sync(job: Callable[[], None]) -> None:
    job()


def _lookup(monkeypatch: pytest.MonkeyPatch, bench: _Bench, **kwargs: Any) -> VoiceLookup:
    monkeypatch.setattr("web.voice_lookup.Bench", bench)
    monkeypatch.setattr("web.voice_lookup.native_picture", lambda *_a: None)
    engines = FakeTorrentEngines(FakeTorrentEngine())
    return VoiceLookup(engines=engines, **kwargs)


def test_a_slow_build_answers_nothing_yet_and_says_it_is_still_coming(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lookup = _lookup(monkeypatch, _Bench(_MEDIA), spawn=lambda _job: None)

    assert lookup.of(_PLAN, "film", _CONFIG) == (None, True)


def test_the_tracks_come_back_and_only_the_chosen_release_stays_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    heard, coming = lookup.of(_PLAN, "film 2010", _CONFIG)

    assert coming is False
    assert heard is not None
    assert heard.media.tracks == _MEDIA.tracks
    assert bench.asked[0][1].title_query == "film 2010"
    assert [profile.key for profile in bench.profiles] == ["q70d"], "судит профилем показа"
    assert [prep.found for prep in bench.kept] == [_MEDIA] and bench.dropped == []
    lookup.of(_PLAN, "film 2010", _CONFIG)
    assert len(bench.asked) == 1


def test_a_card_opened_again_warms_the_release_it_already_chose(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)
    heard, _coming = lookup.of(_PLAN, "film", _CONFIG)
    assert heard is not None

    lookup.warms.leave(_PLAN.picture.key)
    again, coming = lookup.of(_PLAN, "film", _CONFIG)

    assert bench.dropped == [True], "ушла карточка - ушёл и прогрев"
    assert again is heard and coming is False
    assert len(bench.asked) == 2
    assert bench.asked[1][1].card_release == heard.release


def test_a_refused_release_is_an_empty_answer_until_the_retry_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _Clock()
    bench = _Bench(InfraError("no fit"))
    lookup = _lookup(monkeypatch, bench, spawn=_sync, clock=clock)

    assert lookup.of(_PLAN, "film", _CONFIG) == (None, False)
    assert bench.dropped == [True] and bench.kept == []
    lookup.of(_PLAN, "film", _CONFIG)
    assert len(bench.asked) == 1

    clock.now += RETRY + 1
    bench.answer = _MEDIA
    heard, _coming = lookup.of(_PLAN, "film", _CONFIG)

    assert heard is not None
    assert len(bench.asked) == 2


def test_a_shelf_reads_an_infrastructure_failure_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Карточка получает свой пустой ответ, полка - честное «не знаю»."""
    lookup = _lookup(monkeypatch, _Bench(InfraError("source down")), spawn=_sync)

    assert lookup.shelf_of(_PLAN, "film", _CONFIG) == (None, False, False)


def test_a_shelf_reads_a_release_without_tracks_as_a_known_empty_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Стенд дочитал раздачу и дорожек не нашёл - это честный ответ, а не отказ источника."""
    lookup = _lookup(monkeypatch, _Bench(NotFoundError("no tracks")), spawn=_sync)

    assert lookup.shelf_of(_PLAN, "film", _CONFIG) == (None, False, True)


def test_a_shelf_reads_a_queue_whose_swarms_all_kept_silent_as_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Рой не ответил ни у одной тронутой раздачи: о картине не известно ничего.

    Под нагрузкой DHT так молчат и живые раздачи («Унабомбер» играл в 17 приговорах из 18),
    и «не играет» снимало бы с полки годную плитку.
    """
    silence = NotFoundError("swarm kept silent")
    silence.swarm = True
    lookup = _lookup(monkeypatch, _Bench(silence), spawn=_sync)

    assert lookup.shelf_of(_PLAN, "film", _CONFIG) == (None, False, False)


_KEPT = Release(raw_name="Film 2010 1080p", title="Film", magnet="magnet:?xt=urn:btih:" + "a" * 40)
_KEPT_PLAN = Plan(picture=_PICTURE, ranked=[_RELEASE, _KEPT], runtime=0, warn_mbit=0)


def _live(**rest: Any) -> Entry:
    return Entry(**{"title": "Film", "magnet": _KEPT.magnet, "dur": 7200.0, "pos": 180.0, **rest})


def test_a_live_bookmark_card_lists_the_tracks_of_the_bookmark_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Играть продолжит закладку - меню, отметка и прогрев принадлежат её раздаче."""
    bench = _Bench(_MEDIA, release=_KEPT)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    heard, _coming = lookup.of(_KEPT_PLAN, "film", _CONFIG, _live())

    asked = bench.asked[0][1]
    assert (asked.release, asked.release_hash) == (2, "a" * 40), "раздача закладки названа"
    assert heard is not None and heard.release == "a" * 40


def test_a_honestier_pick_may_not_replace_the_bookmark_release_of_a_live_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Свободный отбор брал бы другой релиз - карточка с закладкой спрашивает её раздачу.

    «Интерстеллар» с закладкой на раздаче, чьё имя обещало 1080p, а ffprobe мерил 648p:
    честностная проверка подменяла ответ, закладка оставалась без меню. Названную
    раздачу проверка не трогает - меню показывает дорожки той, что продолжит «Играть».
    """

    @dataclass
    class _Honest(_Bench):
        """Свободный выбор - лучший релиз; названная раздача возвращается как есть."""

        def resolve(self, plan: Plan, args: Any, _progress: object) -> _Prep:
            self.asked.append((plan, args))
            if isinstance(self.answer, Exception):
                raise self.answer
            if args.release_hash:
                return _Prep(self.answer, plan.ranked[(args.release or 1) - 1])
            return _Prep(self.answer, self.release)

    bench = _Honest(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    heard, coming = lookup.of(_KEPT_PLAN, "film", _CONFIG, _live())

    assert coming is False
    assert heard is not None and heard.release == "a" * 40
    assert heard.media.tracks == _MEDIA.tracks, "дорожки - раздачи закладки, не чужой"
    assert [prep.found for prep in bench.kept] == [_MEDIA], "греется раздача закладки"


def test_a_card_picked_before_the_bookmark_is_picked_again_for_the_bookmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)
    first, _coming = lookup.of(_KEPT_PLAN, "film", _CONFIG)
    assert first is not None and first.release != "a" * 40

    lookup.warms.leave(_PICTURE.key)
    bench.release = _KEPT
    heard, _coming = lookup.of(_KEPT_PLAN, "film", _CONFIG, _live())

    assert [asked[1].release_hash for asked in bench.asked] == ["", "a" * 40]
    assert heard is not None and heard.release == "a" * 40


_OWN = media(tracks=(track(0, "rus", "MVO"), track(1, "ukr", "Dub"), track(2, "eng", "Original")))


@dataclass
class _Record:
    """Подмена чтения записи закладки: паспорт по очереди ответов, отказ - исключением."""

    answers: list[Any]
    read: list[Entry] = field(default_factory=list)

    def __call__(self, _config: Config, entry: Entry) -> Any:
        self.read.append(entry)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


def test_a_bookmark_release_gone_from_the_listing_lists_the_tracks_of_its_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Раздачи закладки нет в выдаче, а «Играть» продолжит её магнит: меню - её дорожки.

    Отбор её не найдёт и возьмёт чужую; дорожки читаются из записи показа, мимо отбора.
    """
    bench, record, heads = _Bench(_MEDIA), _Record([_OWN]), []
    lookup = _lookup(
        monkeypatch, bench, spawn=_sync, kept_media=record, head=lambda *a: heads.append(a)
    )
    live = _live()

    heard, coming = lookup.of(_PLAN, "film", _CONFIG, live)

    assert coming is False and record.read == [live]
    assert heard is not None and heard.release == "a" * 40 and heard.media is _OWN
    assert bench.asked == [] and heads == [], "чужую раздачу отбор не поднимал"
    assert not lookup.warms.holds(_PICTURE.key)


def test_a_failed_read_of_the_bookmark_record_is_asked_again_after_the_retry_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Рой закладки промолчал - это «не знаю»: ноль не держится дольше :data:`RETRY`."""
    clock = _Clock()
    record = _Record([InfraError("no peers"), _OWN])
    lookup = _lookup(monkeypatch, _Bench(_MEDIA), spawn=_sync, kept_media=record, clock=clock)

    assert lookup.of(_PLAN, "film", _CONFIG, _live()) == (None, False)
    assert lookup.of(_PLAN, "film", _CONFIG, _live()) == (None, False)
    clock.now += RETRY + 1
    heard, _coming = lookup.of(_PLAN, "film", _CONFIG, _live())

    assert len(record.read) == 2 and heard is not None and heard.media is _OWN


def test_a_show_bookmark_warms_its_own_episode_and_a_finished_film_does_not_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA, release=_KEPT)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)
    show = _live(kind="tv", season=2, episode=5, pos=0.0, episodes=[[2, 4, 0], [2, 5, 1]])

    lookup.of(_KEPT_PLAN, "film", _CONFIG, show)
    other = Picture(title="Other", year=2011, kind="movie", releases=[_RELEASE])
    lookup.of(
        Plan(picture=other, ranked=[_RELEASE], runtime=0, warn_mbit=0),
        "o",
        _CONFIG,
        _live(done=True),
    )

    episode = bench.asked[0][1].episode
    assert (episode.season, episode.episode) == (2, 5)
    assert bench.asked[1][1].card_release == ""


@dataclass
class _Choosing(_Bench):
    """Отбор карточки, который идёт, пока тест его не отпустит: спрашивает индикатор по кругу."""

    profile: Any = None
    choose: Any = None
    preps: dict[Any, Any] = field(default_factory=dict)
    entered: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)

    def resolve(self, plan: Plan, args: Any, progress: Any) -> _Prep:
        self.asked.append((plan, args))
        self.entered.set()
        while not self.done.wait(0.01):
            progress.phase("метаданные")
        return _Prep(self.answer, self.release)


@pytest.mark.machine
def test_a_show_clicked_while_the_card_chooses_takes_the_card_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Клик во время отбора карточки ждёт его итога и берёт тот же стенд, второго не заводит.

    Снятый отбор карточки терял то, за чем она уже сходила в рой, а показ начинал тот же
    отбор заново рядом с греющимся стендом.
    """
    bench = _Choosing(_MEDIA)
    threads: list[threading.Thread] = []

    def spawn(job: Callable[[], None]) -> None:
        threads.append(threading.Thread(target=job, daemon=True))
        threads[-1].start()

    lookup = _lookup(monkeypatch, bench, spawn=spawn)
    lookup.of(_PLAN, "film", _CONFIG)
    assert bench.entered.wait(5.0)

    fresh: Any = _Choosing(_MEDIA)
    taken: list[Any] = []
    caller = threading.Thread(
        target=lambda: taken.append(lookup.warms.take(_PICTURE.key, fresh)), daemon=True
    )
    caller.start()
    caller.join(0.2)
    assert caller.is_alive() and taken == [], "клик снял отбор карточки или завёл второй стенд"

    bench.done.set()
    caller.join(5.0)
    threads[0].join(5.0)
    assert taken == [bench] and fresh.asked == [], "показ берёт стенд карточки, а не свой"
    lookup.spawn = lambda _job: None  # карточка открыта заново: прогрев уже не про этот тест
    assert lookup.of(_PLAN, "film", _CONFIG)[0] is not None, "дорожки - от итога карточки"
    assert bench.dropped == [] and bench.kept == [], "стенд у показа: карточка его не трогает"


def test_a_bookmark_card_warms_the_bookmark_place_not_the_file_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Оно» продолжалось с 395 с, а прогрев карточки тянул начало: первый сегмент ждал рой."""
    bench = _Bench(_MEDIA, release=_KEPT)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    lookup.of(_KEPT_PLAN, "film", _CONFIG, _live(pos=395.0))

    assert getattr(bench, "resume", None) == 395.0


def test_a_card_without_a_live_bookmark_warms_the_file_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync)

    lookup.of(_PLAN, "film", _CONFIG, _live(pos=395.0, done=True))

    assert getattr(bench, "resume", None) == 0.0


def test_a_finished_card_pick_starts_the_head_of_the_release_it_keeps_warm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Отбор карточки кончился раньше клика: голова показа греется этой же раздачей."""
    heads: list[tuple[Any, ...]] = []
    bench = _Bench(_MEDIA)
    lookup = _lookup(monkeypatch, bench, spawn=_sync, head=lambda *args: heads.append(args))

    lookup.of(_PLAN, "film", _CONFIG)

    assert len(heads) == 1
    config, profile, _engines, plan, prep, args, kept = heads[0]
    assert config is _CONFIG and profile.key == "q70d" and plan is _PLAN
    assert prep.found is _MEDIA and args.title_query == "film" and kept is None


def test_a_bookmark_card_lays_the_head_of_the_bookmark_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Играть» продолжит закладку: голова - её запись и место, не выбор отбора."""
    heads: list[tuple[Any, ...]] = []
    bench = _Bench(_MEDIA, release=_KEPT)
    lookup = _lookup(monkeypatch, bench, spawn=_sync, head=lambda *args: heads.append(args))
    live = _live()

    lookup.of(_KEPT_PLAN, "film", _CONFIG, live)

    assert len(heads) == 1 and heads[0][-1] is live


def test_a_refused_card_pick_starts_no_head(monkeypatch: pytest.MonkeyPatch) -> None:
    heads: list[tuple[Any, ...]] = []
    bench = _Bench(InfraError("no fit"))
    lookup = _lookup(monkeypatch, bench, spawn=_sync, head=lambda *args: heads.append(args))

    lookup.of(_PLAN, "film", _CONFIG)

    assert heads == []
