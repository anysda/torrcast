"""Зеркально проверяет цикл серий внутри юнита показа."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from tests.fakes.clock import FakeClock
from tests.fakes.journal import Tape
from tests.fakes.state_store import FakeStateStore
from tests.fakes.stream_source import FakeStreamSource
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.usecases.revive_playback.world import (
    Beat,
    RemoteClosedReceiver,
    feed_with_segments,
)
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.worker_settings import WORKER_META
from torrcast.ports.journal import slot as journal_slot
from torrcast.ports.receiver import Receiver
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases import worker_loop
from torrcast.usecases.following import _following
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.worker_loop import _worker_loop


def test_metadata_budget_of_the_unit_stays_where_it_was() -> None:
    assert WORKER_META == 60.0


def test_the_loop_and_its_next_episode_lookup_are_callable() -> None:
    assert callable(_worker_loop) and callable(_following)


class _EmitTape(Tape):
    """Лента, помнящая и свободные события: снимок порогов уезжает именно ими."""

    def emit(self, phase: str, event: str, **fields: object) -> None:
        self.calls.append((f"{phase}/{event}", dict(fields)))


def test_the_loop_pins_the_thresholds_snapshot_to_the_session_start_record(
    monkeypatch: pytest.MonkeyPatch, _ports_restored: None
) -> None:
    """Снимок порогов уезжает в ленту полями записи о начале сеанса, а не «где-то
    рядом»: иначе недельный разбор читал бы начало показа без чисел, которыми играли."""
    key = "movie:dune:2021"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(
        key,
        Entry(title="Дюна", magnet="magnet:?xt=urn:btih:x", dur=3600.0, depth=8, frame=1080),
    )
    state.save(fresh)
    state_slot.install(state)
    tape = _EmitTape()
    journal_slot.install(tape)
    asked: list[tuple[Config, Profile]] = []

    def snapshot(config: Config, profile: Profile) -> dict[str, object]:
        asked.append((config, profile))
        return {
            "profile_source": "паспорт приёмника",
            "thresholds": {"burst": 60.0},
            "threshold_sources": {"burst": "профиль q70d"},
        }

    monkeypatch.setattr(worker_loop, "_worker_thresholds", snapshot)
    config = Config()

    code = worker_loop._worker_loop(
        config,
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]  # приёмник зовёт только показ, а он здесь подделка
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=lambda *args, **kwargs: 0,
    )

    assert code == 0
    assert asked == [(config, CAUTIOUS)], "снимок снят с настроек и профиля серии"
    start: list[dict[str, Any]] = tape.named("session/session_start")
    assert len(start) == 1, "запись о начале сеанса одна на серию"
    assert start[0]["profile"] == "q70d"
    assert start[0]["profile_source"] == "паспорт приёмника"
    assert start[0]["thresholds"] == {"burst": 60.0}
    assert start[0]["threshold_sources"] == {"burst": "профиль q70d"}


def _shown_title(entry: Entry, _ports: None = None) -> str:
    """Подпись, с которой цикл зовёт показ: ровно она уезжает на экран."""
    key = "tv:harley-quinn:2019"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(key, entry)
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(_EmitTape())
    seen: list[str] = []

    def play(config: Config, source: str, audio: int, about: str, *args: Any, **kw: Any) -> int:
        seen.append(about)
        return 0

    worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]  # приёмник зовёт только показ, а он здесь подделка
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
    )
    return seen[0]


def _harley(**fields: Any) -> Entry:
    return Entry(
        title="Харли Квинн",
        magnet="magnet:?xt=urn:btih:x",
        kind="tv",
        dur=1500.0,
        depth=8,
        frame=1080,
        season=5,
        episode=1,
        episodes=[[5, 1, 0], [5, 2, 1]],
        **fields,
    )


def test_a_forced_voice_swap_reaches_the_screen_and_not_the_terminal(
    _ports_restored: None,
) -> None:
    """Зритель смотрит в телевизор: подпись показа - единственное, что туда уезжает."""
    shown = _shown_title(_harley(studio="The Kitchen Russia", heard="TVShows"))

    assert shown == "Харли Квинн s5e1 · voice TVShows instead of The Kitchen Russia"


def test_a_show_without_a_swap_carries_no_extra_word(_ports_restored: None) -> None:
    """Подмены нет - и приписывать подписи нечего: молчаливых подмен не бывает, лишних тоже."""
    assert _shown_title(_harley(studio="The Kitchen Russia")) == "Харли Квинн s5e1"


def test_a_finished_season_is_continued_by_the_next_one(
    monkeypatch: pytest.MonkeyPatch, _ports_restored: None
) -> None:
    """Конец раздачи сезона - не конец показа: цикл играет сезон, записанный поиском."""
    key = "tv:сериал:2020"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(
        key,
        Entry(
            title="Сериал",
            magnet="magnet:?xt=s4",
            kind="tv",
            season=4,
            episode=10,
            dur=1400.0,
            depth=8,
            frame=1080,
            episodes=[[4, 9, 0, 10**9], [4, 10, 1, 10**9]],
        ),
    )
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(Tape())
    monkeypatch.setattr(worker_loop, "_worker_thresholds", lambda *_a: {})
    # Следующая серия своей длительности не знает - её читает пробник; здесь он подделка.
    monkeypatch.setattr(
        "torrcast.usecases.episode_duration._episode_prober",
        lambda *_a, **_k: Media(duration=1400.0, video="h264", height=1080, width=1920),
    )
    played: list[str] = []

    def play(
        _c: object, _s: object, _a: object, title: str, _clock: object, watch: Any, **_kw: object
    ) -> int:
        played.append(title)
        watch.done = True  # серия доиграла до конца: сторож пишет «досмотрено»
        keeper = state_slot.store()
        now = keeper.load()
        now.put(key, watch.entry.advance())
        keeper.save(now)
        return 0

    searches: list[str] = []

    def next_season(_config: object, asked: str, *_rest: object) -> bool:
        searches.append(asked)
        if len(searches) > 1:
            return False  # шестого сезона в природе нет
        keeper = state_slot.store()
        now = keeper.load()
        now.put(
            key,
            Entry(
                title="Сериал",
                magnet="magnet:?xt=s5",
                kind="tv",
                season=5,
                episode=1,
                dur=1400.0,
                depth=8,
                frame=1080,
                episodes=[[5, 1, 0, 10**9], [5, 2, 1, 10**9]],
            ),
        )
        keeper.save(now)
        return True

    code = worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
        next_season=next_season,
    )

    assert code == 0
    assert played == ["Сериал s4e10", "Сериал s5e1", "Сериал s5e2"], (
        "сезон 5 продолжил показ сам, а внутри него стык серий работает как прежде"
    )
    assert searches == [key, key], "поиск следующего сезона - один раз на конец сезона"


def _homemakers(**fields: Any) -> Entry:
    return Entry(
        title="Домохозяйки",
        magnet="magnet:?xt=urn:btih:x",
        kind="tv",
        dur=2600.0,
        depth=8,
        frame=1080,
        season=1,
        episode=7,
        episodes=[[1, 7, 0], [1, 8, 1]],
        **fields,
    )


def test_a_show_closed_by_the_remote_moves_the_bookmark_without_raising_the_receiver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _ports_restored: None,
) -> None:
    """TC-880: закрытый с пульта показ двигает закладку на s1e8, а приёмник не поднимает.

    🔴 Признак закрытия руками в сторожа тут не кладут: он обязан пройти всю цепочку -
    пустой экран приёмника → :func:`_closed` → настоящий :class:`Watch` → цикл юнита.
    Проставленный тестом признак мерил бы одно последнее звено, а вся ценность правки
    живёт в тех, что до него: убери проводку из продукта, и такой тест промолчит.
    """
    key = "tv:домохозяйки:2020"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(key, _homemakers())
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(Tape())
    # Длительность следующей серии читает пробник: с настоящим цикл упёрся бы в сеть
    # раньше, чем сказал бы, поднял он приёмник или нет.
    monkeypatch.setattr(
        "torrcast.usecases.episode_duration._episode_prober",
        lambda *_a, **_k: Media(duration=2600.0, video="h264", height=1080, width=1920),
    )
    played: list[str] = []

    def play(
        _c: object, _s: object, _a: object, title: str, _clock: object, watch: Any, **_kw: object
    ) -> int:
        played.append(title)
        # Круг опроса настоящий: кадр на 2569 с (99 % серии), а следом пустой экран -
        # ровно то, что видит показ, когда зритель убрал его пультом.
        receiver = RemoteClosedReceiver(
            [(2569.0, "PLAYING", False), (0.0, "UNKNOWN", True)], dur=2600.0
        )
        _hold(
            cast(Receiver, receiver),
            feed_with_segments(tmp_path / title),
            watch,
            clock=FakeClock(now=1000.0),
        )
        watch.close()
        return 0

    code = worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
    )

    assert code == 0
    assert played == ["Домохозяйки s1e7"], "приёмник поднят только для закрытой серии, не для s1e8"
    following = _following(key)
    assert following is not None and following.episode == 8, "закладка всё же сдвинута на s1e8"


def test_a_show_closed_by_the_remote_on_the_credits_does_not_raise_the_receiver(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _ports_restored: None,
) -> None:
    """🔴 TC-880: тот же жест НА ТИТРАХ приёмник тоже не будит.

    Отличие от жеста в середине серии ровно одно, и оно решает всё: признак закрытия
    приезжает не первым тёмным опросом, а следующим. Жест роняет сокет 8009 вместе с
    приложением, и первый тёмный ответ - эхо прошлого опроса (:attr:`Beat.stale`): экран
    в нём числится нашим, а показ незакрытым. В середине серии следующий круг показу
    дарит лестница подъёма, а на титрах она же его и отнимала - ``ending_reached``
    возвращал «гаснем» до всякого разбора, и цикл юнита заводил следующую серию.

    Живой замер на приставке 30-08-2026 (жест = ``am force-stop`` приложения приёмника):
    ``upd=ERR:NotConnected``, ``closed=False`` первым опросом и ``closed=True`` следующим.
    Сценарий ниже - эти самые три круга.

    🔴 Признак закрытия руками в сторожа не кладут: он обязан пройти всю цепочку -
    невнятный ответ приёмника → внятный → :func:`_closed` → настоящий :class:`Watch` →
    цикл юнита. Проставленный тестом признак мерил бы одно последнее звено (TC-899).
    """
    key = "tv:домохозяйки-титры:2020"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(key, _homemakers())
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(Tape())
    monkeypatch.setattr(
        "torrcast.usecases.episode_duration._episode_prober",
        lambda *_a, **_k: Media(duration=2600.0, video="h264", height=1080, width=1920),
    )
    played: list[str] = []

    def play(
        _c: object, _s: object, _a: object, title: str, _clock: object, watch: Any, **_kw: object
    ) -> int:
        played.append(title)
        receiver = RemoteClosedReceiver(
            [
                (2569.0, "PLAYING", False),  # 98.8 % серии: показ уже на титрах
                Beat(0.0, "UNKNOWN", stale=True),  # жест: сокет лёг, ответ - эхо прошлого
                Beat(0.0, "UNKNOWN", closed=True),  # приёмник переподключился и назвал волю
            ],
            dur=2600.0,
        )
        _hold(
            cast(Receiver, receiver),
            feed_with_segments(tmp_path / title, whole=2600.0),
            watch,
            clock=FakeClock(now=1000.0),
        )
        watch.close()
        return 0

    code = worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
    )

    assert code == 0
    assert played == ["Домохозяйки s1e7"], "приёмник поднят только для закрытой серии, не для s1e8"
    following = _following(key)
    assert following is not None and following.episode == 8, "закладка всё же сдвинута на s1e8"


def test_a_stream_that_ended_by_itself_hands_over_at_once_and_costs_no_extra_poll(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    _ports_restored: None,
) -> None:
    """🔴 Контрольная сторона и цена стыка разом: серия доиграла сама - переход штатный.

    Тот же конец картины, что и в проверке выше, но ответ приёмника ВНЯТНЫЙ (живой замер:
    ``IDLE/FINISHED``, статус взят свежим). Такой конец обязан разбираться сразу, как и до
    правки: выдержка :data:`WILL_LIMIT` копится только на эхе мёртвого сокета.

    🔴 Цена названа числом кругов опроса, а не словами: их ровно два, столько же, сколько
    показ тратил до правки. Лишний круг на КАЖДОМ конце серии откладывал бы переход, а
    переход по спеке дороже хвоста - молчаливое замедление стыка тут и ловится.
    """
    key = "tv:домохозяйки-сама:2020"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(key, _homemakers())
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(Tape())
    monkeypatch.setattr(
        "torrcast.usecases.episode_duration._episode_prober",
        lambda *_a, **_k: Media(duration=2600.0, video="h264", height=1080, width=1920),
    )
    played: list[str] = []
    seen: list[RemoteClosedReceiver] = []

    def play(
        _c: object, _s: object, _a: object, title: str, _clock: object, watch: Any, **_kw: object
    ) -> int:
        played.append(title)
        receiver = RemoteClosedReceiver(
            [
                (2569.0, "PLAYING", False),  # 98.8 % серии: показ на титрах
                Beat(0.0, "IDLE"),  # поток кончился сам, и приёмник сказал это внятно
            ],
            dur=2600.0,
        )
        seen.append(receiver)
        _hold(
            cast(Receiver, receiver),
            feed_with_segments(tmp_path / title, whole=2600.0),
            watch,
            clock=FakeClock(now=1000.0),
        )
        watch.close()
        return 0

    code = worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
    )

    assert code == 0
    assert played == ["Домохозяйки s1e7", "Домохозяйки s1e8"], "обе серии поднялись на приёмнике"
    assert [r.polls for r in seen] == [2, 2], "внятный конец разобран сразу, лишних кругов нет"


def test_a_naturally_ended_show_still_raises_the_next_episode(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], _ports_restored: None
) -> None:
    """Поток доиграл сам - следующая серия по-прежнему поднимается на приёмнике.

    Переход между сериями зритель видит как обрыв: картинка гаснет и поднимается заново.
    Строка «следующая серия: {label}» - единственное, что отличает решение цикла от
    падения показа, и потому она проверяется вместе с самим переходом.
    """
    key = "tv:домохозяйки-натурально:2020"
    state = FakeStateStore()
    fresh = state.load()
    fresh.put(key, _homemakers())
    state.save(fresh)
    state_slot.install(state)
    journal_slot.install(Tape())
    # Следующая серия своей длительности не знает - её читает пробник; здесь он подделка.
    monkeypatch.setattr(
        "torrcast.usecases.episode_duration._episode_prober",
        lambda *_a, **_k: Media(duration=2600.0, video="h264", height=1080, width=1920),
    )
    played: list[str] = []

    def play(
        _c: object, _s: object, _a: object, title: str, _clock: object, watch: Any, **_kw: object
    ) -> int:
        played.append(title)
        watch.entry.pos = watch.entry.dur  # доиграно до конца самим потоком
        watch.entry.moved = True
        watch.close()  # closed_by_remote остаётся False
        return 0

    code = worker_loop._worker_loop(
        Config(),
        key,
        FakeTorrentEngine(),
        None,  # type: ignore[arg-type]
        FakeStreamSource(),
        [],
        CAUTIOUS,
        play=play,
    )

    assert code == 0
    assert played == ["Домохозяйки s1e7", "Домохозяйки s1e8"], "обе серии поднялись на приёмнике"
    assert phrase("worker.next_episode", label="s1e8") in capsys.readouterr().out, (
        "переход к следующей серии назван вслух, а не сделан молча"
    )
