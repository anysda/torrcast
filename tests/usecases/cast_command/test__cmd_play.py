"""Зеркало счастливого пути: ранние выходы отвечают показом, а не проваливаются в поиск."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.fakes import composition
from tests.usecases.cast_command.world import GB, entry, release
from torrcast.domain._series import _Series
from torrcast.domain.args import Args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.domain.media import Media
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store.slot import store as watch_store
from torrcast.usecases.cast_command._choose import _choose
from torrcast.usecases.cast_command._cmd_play import _cmd_play
from torrcast.usecases.choice._named import _title
from torrcast.usecases.choice._passport import _Passport
from torrcast.usecases.following import _following
from torrcast.usecases.select._continue import _continue
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench
from torrcast.usecases.start_clock import _Clock


@pytest.fixture(autouse=True)
def _outside(monkeypatch: pytest.MonkeyPatch) -> None:
    """Паспорт приёмника на стенде спрашивать не у кого: профиль называется прямо.

    Настройки, уборка сирот и строка о занятом телевизоре тут настоящие: файл настроек
    свой у каждого теста, сирот в пустом состоянии нет, а занятого показа нет тем более.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "стенд"))


def _remember(saved: object) -> None:
    state = WatchState()
    state.put("кино", saved)  # type: ignore[arg-type]
    watch_store().save(state)


def _never(*_args: object, **_rest: object) -> int:
    return pytest.fail("до поиска доходить нечему")


def test_a_saved_movie_is_continued_without_a_single_question() -> None:
    """Начатый фильм продолжается молча: до поиска этот путь не доходит вовсе."""
    _remember(entry(query="кино"))

    code = _cmd_play(Args(query=["кино"]), resume=lambda *args, **rest: EXIT_OK, choose=_never)

    assert code == EXIT_OK


def test_an_unnamed_show_resumes_the_latest_serial_not_the_newer_movie() -> None:
    """Пустой запрос получает имя в сценарии и дальше идёт обычной дорогой resume."""
    state = WatchState()
    state.entries["tv:кино:2022"] = entry(
        query="кино",
        kind="tv",
        season=1,
        episode=2,
        episodes=[[1, 1, 0, GB], [1, 2, 1, GB]],
        updated="2026-09-01",
    )
    state.entries["movie:новинка:2026"] = entry(query="новинка", updated="2026-09-02")
    watch_store().save(state)
    resumed: list[str] = []

    def resume(_config: object, key: str, *_args: object, **_rest: object) -> int:
        resumed.append(key)
        return EXIT_OK

    args = Args(query=[])
    code = _cmd_play(args, resume=resume, choose=_never)

    assert code == EXIT_OK
    assert args.query == ["кино"]
    assert resumed == ["tv:кино:2022"]


def test_a_watched_movie_is_started_over_and_says_so() -> None:
    """Досмотренный фильм играется с начала - и это тоже ранний выход, а не поиск."""
    _remember(entry(query="кино", pos=7100.0))

    code = _cmd_play(Args(query=["кино"]), restart=lambda *args, **rest: EXIT_OK, choose=_never)

    assert code == EXIT_OK


def test_an_asked_menu_outranks_the_bookmark_and_says_nothing_about_it(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """``--menu`` - запрос «дай выбрать»: закладка на него не отвечает и не считает."""
    _remember(entry(query="кино", pos=7100.0))

    code = _cmd_play(
        Args(query=["кино"], menu=True),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: EXIT_OK,
    )

    assert code == EXIT_OK
    assert "досмотрено" not in capsys.readouterr().out


def test_a_hand_named_menu_item_outranks_the_bookmark() -> None:
    """``--pick N`` называет картину номером - съесть этот номер закладке нечем."""
    _remember(entry(query="кино"))

    code = _cmd_play(
        Args(query=["кино"], pick=3),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: EXIT_OK,
    )

    assert code == EXIT_OK


def test_the_code_of_the_bookmark_of_the_chosen_picture_reaches_the_caller() -> None:
    """Закладка выбранной картины отвечает показом - и её код уезжает наружу целым."""
    assert _cmd_play(Args(query=["кино"]), choose=lambda *args, **rest: EXIT_OK) == EXIT_OK


def test_a_hand_named_release_searches_the_bookmarked_episode_not_the_first() -> None:
    """``--release N`` у начатого сериала: в поиск уезжает серия закладки, а не s1e1."""
    _remember(
        entry(
            query="кино",
            kind="tv",
            season=5,
            episode=1,
            pos=265.0,
            episodes=[[5, 1, 0, 10**9], [5, 2, 1, 10**9]],
        )
    )
    seen: list[Args] = []

    def choose(_config: object, args: Args, *_rest: object, **_kw: object) -> int:
        seen.append(args)
        return EXIT_OK

    code = _cmd_play(Args(query=["кино"], release=2), restart=_never, resume=_never, choose=choose)

    assert code == EXIT_OK
    assert str(seen[0].episode) == "s5e1", "место в сериале - не выбор раздачи (TC-807)"


def test_the_played_file_names_the_episode_and_the_place_is_carried(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Пак пятого сезона под запросом «s1e1»: строка зовёт серию по ФАЙЛУ (TC-807)."""
    _remember(
        entry(
            query="кино",
            kind="tv",
            season=5,
            episode=1,
            pos=265.0,
            dur=1400.0,
            episodes=[[5, 1, 3, 10**9], [5, 2, 4, 10**9]],
        )
    )
    files = [
        TorrFile(index=3, name="кино/s05e01.mkv", size=8 * GB),
        TorrFile(index=4, name="кино/s05e02.mkv", size=8 * GB),
    ]
    pack = release("Кино / Movie WEB-DL 1080p")
    one = Plan(
        picture=Picture(title="Кино", year=1999, kind="tv", releases=[pack]),
        ranked=[pack],
        runtime=1400.0,
        warn_mbit=16.0,
        series=_Series(want=Episode(1, 1)),
    )
    prep = _Prep(number=1, release=pack)
    prep.video, prep.files = files[0], files
    prep.media = Media(
        duration=1400.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )

    class _Bench:
        def drop_all(self) -> None:
            pass

    class _Passport:
        def get(self) -> Origin:
            return Origin()

    def choose(*_args: object, **_kw: object) -> object:
        return [one], one, prep, _Bench(), _Passport()

    code = _cmd_play(
        Args(query=["кино"], release=1, dry=True),
        restart=_never,
        resume=_never,
        choose=choose,  # type: ignore[arg-type]
    )

    assert code == EXIT_OK
    out = capsys.readouterr().out
    named = phrase("choice.quoted", it=_title(one.picture))
    assert f"{named} s5e1" in out, "подпись серии - у файла, который играет, а не у запроса"
    tail = phrase("cmd_play.resumed_from", pos="0:04:25")
    assert tail in out, "место закладки названо обычной строкой показа"


class _Facts:
    """Справка к меню, которой нечего сказать: путь до релиза считает по своим числам."""

    def __init__(self, wanted: object) -> None:
        self.wanted = wanted

    def start(self) -> None:
        return None

    def finish(self) -> None:
        return None

    def get(self, *_rest: object) -> Fact:
        return Fact()


class _OnePassport:
    def get(self) -> Origin:
        return Origin()


class _OneBench:
    """Стенд отбора, который отдаёт один готовый релиз и ничего не греет."""

    def __init__(self, prep: _Prep) -> None:
        self.prep = prep

    def start(self, plan: Plan, number: int) -> None:
        return None

    def spare(self, plan: Plan, args: object) -> list[object]:
        return []

    def reorder(self, plan: Plan, *_rest: object) -> Plan:
        return plan

    def keep_plan(self, plan: Plan) -> None:
        return None

    def keep_only(self, prep: _Prep) -> None:
        return None

    def resolve(self, plan: Plan, args: object, progress: object) -> _Prep:
        return self.prep

    def drop_all(self) -> None:
        return None


def test_a_series_recognised_by_the_files_of_the_release_reaches_the_bookmark(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TC-854: раздача с явными номерами серий делает картину сериалом - и это доезжает
    до закладки, поэтому очередь серий поднимается и после перезапуска.

    🔴 ``recognize_series`` тут не зовут: его обязан позвать сам путь до релиза. Тест,
    зовущий метод своей строкой, мерит метод, а вся ценность правки живёт в одной строке
    проводки - в той, где выбранной картине меняют вид уже прочитанными метаданными.
    Имя раздачи о сериях молчит, поэтому без этой строки в закладке остаётся фильм: ни
    серии, ни таблицы серий, ни очереди - играть дальше нечего по построению.
    """
    composition.use_facts(monkeypatch, _Facts)
    composition.use_engines(monkeypatch, lambda url, timeout=30.0: object())
    started: list[str] = []
    composition.use_start_unit(monkeypatch, started.append)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )
    pack = release("Врата Штейна / Steins;Gate WEB-DL 1080p")
    one = Plan(
        picture=Picture(title="Врата Штейна", year=2011, kind="movie", releases=[pack]),
        ranked=[pack],
        runtime=1400.0,
        warn_mbit=16.0,
    )
    files = [
        TorrFile(index=1, name="Врата Штейна/s01e01.mkv", size=8 * GB),
        TorrFile(index=2, name="Врата Штейна/s01e02.mkv", size=8 * GB),
    ]
    prep = _Prep(number=1, release=pack)
    prep.video, prep.files = files[0], files
    prep.media = Media(
        duration=1400.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )
    bench = _OneBench(prep)

    def choose(
        config: Config,
        args: Args,
        chosen: Choice,
        state: WatchState,
        live: tuple[str, Entry] | None,
        clock: _Clock,
    ) -> tuple[list[Plan], Plan, _Prep, Bench, _Passport] | int:
        """Настоящий путь до релиза: подделаны круг поиска, стенд, справка и ответ меню."""
        return _choose(
            config,
            args,
            chosen,
            state,
            live,
            clock,
            circle=lambda *_a, **_k: [one],
            stand=lambda *_a, **_k: cast(Bench, bench),
            passport_of=lambda _plans: cast(_Passport, _OnePassport()),
            pick=lambda *_a, **_k: one,
            bookmark=lambda *_a, **_k: None,
        )

    code = _cmd_play(Args(query=["врата штейна"]), restart=_never, resume=_never, choose=choose)

    assert code == EXIT_OK
    assert started == [one.picture.key], "показ уехал в юнит под ключом уточнённой картины"
    saved = watch_store().load().get(one.picture.key)
    assert saved is not None, "запись показа обязана лечь под тем же ключом"
    assert saved.kind == "tv", "закладка помнит сериал, а не фильм имени раздачи"
    assert (saved.season, saved.episode) == (1, 1), "и серию, с которой сериал начали"
    assert [row[:3] for row in saved.episodes] == [[1, 1, 1], [1, 2, 2]], (
        "таблица серий в закладке - вся раздача, а не один сыгранный файл"
    )
    assert _following(one.picture.key) is not None, (
        "без вида «сериал» очереди серий нет по построению: играть дальше нечего"
    )


def test_a_healthy_recording_never_takes_the_trip_to_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Здоровая запись играет как играла: поход в поиск считается, и счёт его - ноль.

    Мерится вся цепочка целиком - настоящее продолжение и настоящий приговор раздаче, -
    потому что ложный отказ виден только здесь: подделан ровно рой, который отвечает
    файлами, как отвечал бы живой. Считается при этом не исход (он был бы тем же и через
    поиск), а дорога: лишний поход стоил бы зрителю минуты под меню.
    """
    _remember(entry(query="кино"))
    trips = 0

    class _Swarm:
        def __call__(self, url: str, timeout: float = 30.0) -> _Swarm:
            return self

        def add(self, magnet: str) -> str:
            return "hash-кино"

        def wait_files(self, *_args: object, **_kw: object) -> list[TorrFile]:
            return [TorrFile(index=0, name="кино/кино.mkv", size=8 * GB)]

    composition.use_engines(monkeypatch, _Swarm())

    def resume(*args: object, **rest: object) -> int | None:
        return _continue(*args, resume=lambda *a, **k: EXIT_OK, **rest)  # type: ignore[arg-type]

    def choose(*_args: object, **_kw: object) -> int:
        nonlocal trips
        trips += 1
        return EXIT_OK

    code = _cmd_play(Args(query=["кино"]), resume=resume, choose=choose)

    assert code == EXIT_OK
    assert trips == 0, "обычный путь для здоровой записи не открывается вовсе"


def test_the_place_of_a_dead_recording_moves_onto_the_release_found_instead(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 TC-571. Умирает релиз, а не закладка: место записи доезжает до новой раздачи.

    Продолжение уступило поиску, похоронив записанный магнит, - и час просмотра обязан
    оказаться на том релизе, который поиск нашёл взамен. Иначе цена автоматики - потерянная
    закладка, а это ровно та ценность, ради которой запись и ведётся.
    """
    # Ключ записи - это ключ КАРТИНЫ: под ним её кладёт показ, под ним же место и ищется.
    saved = WatchState()
    saved.put(Picture(title="Кино", year=1999).key, entry(query="кино", pos=3600.0, dur=7200.0))
    watch_store().save(saved)

    def resume(_config: object, _key: object, saved: object, args: Args, **_kw: object) -> None:
        args.bury(entry(query="кино").magnet)  # так уступает продолжение мёртвой раздаче
        return None

    other = replace(release("Кино / Movie (1999) WEB-DL 1080p"), magnet="magnet:?xt=другая-раздача")
    one = Plan(
        picture=Picture(title="Кино", year=1999, releases=[other]),
        ranked=[other],
        runtime=7200.0,
        warn_mbit=16.0,
    )
    prep = _Prep(number=1, release=other)
    prep.video = TorrFile(index=0, name="кино/кино.mkv", size=8 * GB)
    prep.files = [prep.video]
    prep.media = Media(
        duration=7200.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )

    class _Bench:
        def drop_all(self) -> None:
            pass

    class _Passport:
        def get(self) -> Origin:
            return Origin()

    code = _cmd_play(
        Args(query=["кино"], dry=True),
        restart=_never,
        resume=resume,
        choose=lambda *args, **rest: ([one], one, prep, _Bench(), _Passport()),  # type: ignore[arg-type]
    )

    assert code == EXIT_OK
    tail = phrase("cmd_play.resumed_from", pos="1:00:00")
    assert tail in capsys.readouterr().out, "час просмотра переехал на новую раздачу"


def test_a_voice_taken_from_a_file_beside_the_video_names_that_file(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Звук взят ВТОРЫМ входом из соседнего файла - и файл назван по имени.

    Решение тут не косметическое: показ идёт двумя входами вместо одного, старт дороже,
    а перемотка ведёт себя иначе. Молчание об этом читается зрителем как поломка звука в
    самой раздаче. Дорожки обоих паспортов названы двумя языками нарочно: искомый звук
    зависит от языка продукта, а предмет теста - вторая ветка входа, а не язык.
    """
    apart = release("Кино / Movie (1999) WEB-DL 1080p")
    one = Plan(
        picture=Picture(title="Кино", year=1999, releases=[apart]),
        ranked=[apart],
        runtime=7200.0,
        warn_mbit=16.0,
    )
    prep = _Prep(number=1, release=apart)
    prep.video = TorrFile(index=0, name="кино/кино.mkv", size=8 * GB)
    prep.voice_file = TorrFile(index=1, name="кино/кино.rus.mka", size=GB // 4)
    prep.files = [prep.video, prep.voice_file]
    prep.media = Media(
        duration=7200.0,
        tracks=(AudioTrack(index=0, language="jpn", title="Оригинал"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )
    prep.voice_media = replace(
        prep.media,
        tracks=(
            AudioTrack(index=0, language="rus", title="Дубляж"),
            AudioTrack(index=1, language="eng", title="Original"),
        ),
    )

    class _Bench:
        def drop_all(self) -> None:
            pass

    class _Passport:
        def get(self) -> Origin:
            return Origin()

    code = _cmd_play(
        Args(query=["кино"], dry=True),
        restart=_never,
        resume=_never,
        choose=lambda *args, **rest: ([one], one, prep, _Bench(), _Passport()),  # type: ignore[arg-type]
    )

    assert code == EXIT_OK
    said = phrase("cmd_play.voice_apart", base="кино.rus.mka")
    assert said in capsys.readouterr().out, "второй вход назван файлом, из которого взят"


def test_a_dead_series_recording_searches_the_bookmarked_episode_not_the_first() -> None:
    """🔴 TC-571. У сериала место - это серия: она встаёт в запрос, куда ушёл поиск.

    Приём тот же, что при названном руками релизе (TC-807): без серии поиск взял бы сезон
    и заиграл бы s5e1... с первой серии сезона, то есть не то, что зритель смотрел.
    """
    _remember(
        entry(
            query="кино",
            kind="tv",
            season=5,
            episode=2,
            pos=265.0,
            episodes=[[5, 1, 0, 10**9], [5, 2, 1, 10**9]],
        )
    )
    seen: list[Args] = []

    def resume(_config: object, _key: object, _saved: object, args: Args, **_kw: object) -> None:
        args.bury(entry(query="кино").magnet)
        return None

    def choose(_config: object, args: Args, *_rest: object, **_kw: object) -> int:
        seen.append(args)
        return EXIT_OK

    code = _cmd_play(Args(query=["кино"]), restart=_never, resume=resume, choose=choose)

    assert code == EXIT_OK
    assert str(seen[0].episode) == "s5e2", "поиск ищет ту серию, на которой зритель стоял"
