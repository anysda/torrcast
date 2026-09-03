"""Зеркало моста: три отказа договора и словесная причина несостоявшегося показа."""

from __future__ import annotations

import signal
from typing import TYPE_CHECKING, Any

import pytest

from hass.bridge import BUSY, NO_NEXT, NO_VOLUME, NOTHING_PLAYING, STOP, VOLUME, Bridge
from hass.posters import Posters
from hass.refused_error import RefusedError
from hass.say import SEEKBY, TOGGLE
from hass.volume import Volume
from tests.fakes.playback_session import FakePlaybackSession
from tests.fakes.state_store import FakeStateStore
from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.adapters.choice_environment import _SystemChoiceEnvironment
from torrcast.domain.args import Args
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.debug_handles import CTL_ENV
from torrcast.domain.entry import Entry
from torrcast.domain.facts.origin import Origin
from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.abandon import slot as abandon_slot
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.discover.search_circle import search_circle

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path


class _Receiver:
    """Приёмник, отвечающий из памяти: настоящий тут звонил бы в сеть."""

    def __init__(self, level: float = 0.3, deaf: bool = False) -> None:
        self.status = type("_Status", (), {"volume_level": level})()
        self.deaf = deaf
        self.wanted: list[float] = []

    def set_volume(self, level: float) -> None:
        if self.deaf:
            raise OSError("приёмник молчит")
        self.wanted.append(level)

    def disconnect(self) -> None:
        return None


class _Posters:
    """Двойник картинок: помнит, что ему показали, и отвечает готовым.

    Настоящий ходит в Википедию фоновым потоком - зеркалу моста нужна не картинка, а то,
    ЧТО мост о показе рассказывает: идущий показ или пустоту, и ссылку на адрес раздачи.
    """

    def __init__(self, answer: tuple[str, str] = ("", "")) -> None:
        self.answer = answer
        self.shown: list[PlaybackSnapshot | None] = []
        self.streams: list[Callable[[], str]] = []
        self.read_as: dict[str, tuple[bytes, str]] = {}
        self.asked: list[str] = []

    def picture(self, shown: PlaybackSnapshot | None, stream: Callable[[], str]) -> tuple[str, str]:
        self.shown.append(shown)
        self.streams.append(stream)
        return self.answer if shown is not None else ("", "")

    def read(self, name: str) -> tuple[bytes, str] | None:
        self.asked.append(name)
        return self.read_as.get(name)


#: Просьба собрать мост со СВОИМ источником картинок, а не с двойником: подделка стоит
#: во всех проверках ниже, и без этой просьбы сборка по умолчанию не мерялась бы нигде.
OWN_POSTERS: Any = object()


def _bridge(
    session: FakePlaybackSession,
    *,
    command: Callable[[Sequence[str] | None], int] = lambda _argv: 0,
    receiver: _Receiver | None = None,
    search: Any = None,
    detect: Any = None,
    settings: Callable[[], Config] | None = None,
    posters: Any = None,
) -> Bridge:
    """Мост на подделках: сеанс показа, приёмник и команда - все свои.

    Очередь команд не подделывается: тест сам зовёт :meth:`Bridge.run_one`, как её зовёт
    точка входа из главного потока. Пока не позвал - команда «поднимается».

    Паспорт приёмника подделывается всегда: настоящий звонит в сеть, а зеркалу поиска
    нужен не звонок, а профиль. Память показанного порядка - НЕ подделка: под ``--pick``
    её читает настоящий выбор, и подмена сделала бы зеркало зеркалом самого себя.
    """
    device: Any = receiver or _Receiver()
    kwargs: dict[str, Any] = {"detect": detect or (lambda _config: Choice(CAUTIOUS, "тест"))}
    if posters is not OWN_POSTERS:
        kwargs["posters"] = posters or _Posters()
    if search is not None:
        kwargs["search"] = search
    return Bridge(
        session=session,
        settings=settings or (lambda: Config(tv="10.0.1.7")),
        volume=Volume("10.0.1.7", connect=lambda _address: device),
        command=command,
        **kwargs,
    )


def test_the_remote_refuses_when_nothing_is_playing() -> None:
    bridge = _bridge(FakePlaybackSession(playing=False))

    with pytest.raises(RefusedError) as refusal:
        bridge.control(TOGGLE, 0.0)

    assert refusal.value.word == NOTHING_PLAYING


def test_the_card_is_told_paused_the_second_the_bridge_says_toggle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пауза с карточки - слово самого моста: опрос следом за командой слышит её.

    Home Assistant переспрашивает состояние сразу после команды
    (``custom_components/torrcast/coordinator.py``, ``async_request_refresh``), и ждать
    стоящей закладки (:data:`hass.motion.STILL_SECONDS`) этому опросу нечего: про свою
    команду мост знает в ту же секунду.
    """
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0, moved=True),
    )
    bridge = _bridge(session)

    assert bridge.state()["state"] == "playing"
    bridge.control(TOGGLE, 0.0)

    assert bridge.state()["state"] == "paused"


def test_the_card_is_told_the_receivers_pause_on_the_very_first_poll() -> None:
    """Пауза ПУЛЬТОМ: запись уже несёт слово приёмника, и мост отвечает им сразу.

    Ни порога стоящей закладки, ни второго опроса: владеющий сендер положил правду в
    запись на переходе, и мосту остаётся её прочесть.
    """
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(
            key="movie:муха", title="Муха", position=60.0, moved=True, paused="PAUSED"
        ),
    )

    assert _bridge(session).state()["state"] == "paused"


def test_the_card_is_told_playing_on_the_first_poll_when_the_record_says_so() -> None:
    """И обратно: запись говорит «играет» - мост отвечает playing первым же опросом."""
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(
            key="movie:муха", title="Муха", position=60.0, moved=True, paused="PLAYING"
        ),
    )

    assert _bridge(session).state()["state"] == "playing"


def test_a_fresh_playing_fact_does_not_talk_over_the_cards_own_pause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Пауза с карточки по-прежнему доходит в ту же секунду, и под фактом тоже.

    Запись скажет «играю» ещё пару секунд - показ узнает решение приёмника на своём
    круге опроса, - и всё это время слово держит защёлка команды.
    """
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(
            key="movie:муха", title="Муха", position=60.0, moved=True, paused="PLAYING"
        ),
    )
    bridge = _bridge(session)

    assert bridge.state()["state"] == "playing"
    bridge.control(TOGGLE, 0.0)

    assert bridge.state()["state"] == "paused"


def test_a_refused_toggle_changes_no_word() -> None:
    """Показа нет - команда отказана, и переворачивать слово мост не вправе."""
    session = FakePlaybackSession(playing=False)
    bridge = _bridge(session)

    with pytest.raises(RefusedError):
        bridge.control(TOGGLE, 0.0)

    session.playing = True
    session.play_key = "movie:муха"
    session.shown = PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0, moved=True)
    assert bridge.state()["state"] == "playing"


def test_a_second_show_while_the_first_is_still_starting_is_refused() -> None:
    bridge = _bridge(FakePlaybackSession())

    bridge.play("матрица")  # команда в очереди, но ещё не сделана: показ поднимается
    with pytest.raises(RefusedError) as refusal:
        bridge.play("муха")

    assert refusal.value.word == BUSY
    assert bridge.run_one()
    assert bridge.play("муха")  # кончился первый - второй берётся


def _remembering(taken: list[list[str]]) -> Callable[[Sequence[str] | None], int]:
    """Команда продукта, которая только запоминает argv: до консоли тут дела нет."""

    def command(argv: Sequence[str] | None) -> int:
        taken.append(list(argv or []))
        return 0

    return command


def _refusal_of_stop(bridge: Bridge) -> str | None:
    """Слово, которым мост отказал в остановке; отказа не было - ``None``."""
    try:
        bridge.control(STOP, 0.0)
    except RefusedError as refusal:
        return refusal.word
    return None


def test_the_stop_is_not_refused_while_a_show_is_still_being_raised() -> None:
    """🔴 TC-1022. «Уже поднимаю показ» - не причина отказать человеку в выходе.

    Живой замер 03-09-2026: подъём умер молча, карточка встала в ``torn``, и кнопка
    выключения отвечала `busy` шесть с половиной минут - у человека не было ни одной
    двери наружу. Занятость главного потока тут не спрашивается, а сам подъём снимается
    юнитом показа: досиживать в очереди чужой бюджет старта просьбе некого.
    """
    session = FakePlaybackSession(playing=True, play_key="movie:муха")
    taken: list[list[str]] = []
    bridge = _bridge(session, command=_remembering(taken))

    bridge.play("муха")  # подъём взят в работу и главный поток им занят

    refused = _refusal_of_stop(bridge)

    assert refused is None, f"остановка отказана словом «{refused}»"
    assert session.stopped == 1, "идущий подъём не снят: очередь до остановки не дойдёт"
    assert bridge.run_one() and bridge.run_one()
    assert taken == [["муха"], [STOP]], f"до продукта доехало не то: {taken}"


def test_the_stop_reaches_the_raise_itself_and_not_only_the_queue() -> None:
    """🔴 TC-1022. Отказ человека обязан дойти до ПОДЪЁМА, а не ждать конца его бюджета.

    Живой замер 03-09-2026: остановку посреди подъёма приняли кодом 204 за 0,00 с, а
    продукт пришёл в ``idle`` через 358 с - подъём досидел весь свой ``START_BUDGET`` и
    погас сам, а карточка всё это время говорила человеку, что показ идёт. Гасить юнит в
    момент отказа было нечего: юнита ещё не существовало, его поднимают через десяток
    секунд после начала подъёма. Значит, отказ - это факт, который спрашивает сам подъём.
    """
    session = FakePlaybackSession(playing=False)
    seen: list[bool] = []

    def command(argv: Sequence[str] | None) -> int:
        del argv
        seen.append(abandon_slot.abandoned())  # ровно то, что спрашивает запуск показа
        return 0

    bridge = _bridge(session, command=command)
    abandon_slot.install(bridge.abandoned)

    bridge.play("муха")  # подъём взят в работу, но главный поток до него ещё не дошёл
    assert _refusal_of_stop(bridge) is None

    assert bridge.run_one() and bridge.run_one()
    assert seen[:1] == [True], f"подъём не узнал, что от него отказались: {seen}"


def test_the_stop_is_not_refused_on_an_empty_screen_either() -> None:
    """Гасить нечего - это ответ продукта, а не повод отказать в самой просьбе."""
    session = FakePlaybackSession(playing=False)
    taken: list[list[str]] = []
    bridge = _bridge(session, command=_remembering(taken))

    refused = _refusal_of_stop(bridge)

    assert refused is None, f"остановка отказана словом «{refused}»"
    assert session.stopped == 0, "подъёма не было, а юнит гасили"
    assert bridge.run_one()
    assert taken == [[STOP]], f"до продукта доехало не то: {taken}"


def test_a_dark_record_left_by_a_dead_show_leaves_the_card_idle() -> None:
    """Показ кончился - кончилась и его темнота: карточке крутить колесо не над чем."""
    session = FakePlaybackSession(playing=False)
    session.shown = PlaybackSnapshot(key="movie:муха", title="Муха", dark_since=1.0)
    bridge = _bridge(session)

    said = bridge.state()["state"]

    assert said == "idle", f"мёртвая запись названа карточке словом «{said}»"


def test_a_film_has_no_next_episode() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["movie:муха"] = Entry(title="Муха", magnet="magnet:?xt=1", kind="movie")
    store.save(state)
    bridge = _bridge(FakePlaybackSession(playing=True, play_key="movie:муха"))

    with pytest.raises(RefusedError) as refusal:
        bridge.next()

    assert refusal.value.word == NO_NEXT


def test_the_last_episode_of_the_release_has_no_next_one_either() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=4,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)
    bridge = _bridge(FakePlaybackSession(playing=True, play_key="tv:чернобыль"))

    with pytest.raises(RefusedError) as refusal:
        bridge.next()

    assert refusal.value.word == NO_NEXT


def test_the_next_episode_is_asked_for_by_the_query_a_human_would_type() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=3,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)
    asked: list[list[str]] = []

    def command(argv: Sequence[str] | None) -> int:
        asked.append(list(argv or []))
        return 0

    bridge = _bridge(FakePlaybackSession(playing=True, play_key="tv:чернобыль"), command=command)

    bridge.next()
    bridge.run_one()

    assert asked == [["чернобыль s1e4"]]


def test_a_deaf_receiver_refuses_the_level_instead_of_pretending() -> None:
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0),
    )
    bridge = _bridge(session, receiver=_Receiver(deaf=True))

    with pytest.raises(RefusedError) as refusal:
        bridge.control(VOLUME, 0.4)

    assert refusal.value.word == NO_VOLUME


def test_a_refused_show_leaves_a_spoken_reason_and_the_next_one_clears_it() -> None:
    spoken = ["ничего не нашлось по запросу «муха»"]

    def command(argv: Sequence[str] | None) -> int:
        del argv
        if spoken:
            print(spoken.pop())
            return 1
        return 0

    bridge = _bridge(FakePlaybackSession(), command=command)

    bridge.play("муха")
    bridge.run_one()
    assert bridge.state()["last_error"] == "ничего не нашлось по запросу «муха»"

    bridge.play("матрица")
    bridge.run_one()
    assert bridge.state()["last_error"] is None


def test_a_command_is_allowed_to_install_a_signal_handler_the_way_cast_does() -> None:
    # 🔴 Ровно та строка, на которой мост молча не играл: `cast` на время команды ставит
    # свой обработчик SIGTERM (:func:`torrcast.cli.answered.answered`), а из рабочего
    # потока это не делается вовсе. Отпусти команду в поток - и вместо показа тут ляжет
    # словами «signal only works in main thread».
    def command(argv: Sequence[str] | None) -> int:
        del argv
        previous = signal.signal(signal.SIGTERM, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, previous)
        return 0

    bridge = _bridge(FakePlaybackSession(), command=command)

    bridge.play("матрица")
    bridge.run_one()

    assert bridge.state()["last_error"] is None


def test_the_command_loop_leaves_when_it_is_asked_to() -> None:
    # 🔴 Уход проверяется тем же вызовом, которым мост живёт: не «поток кончился», а
    # цикл сказал «больше не зовите». Иначе юнит не отпускал бы SIGTERM.
    bridge = _bridge(FakePlaybackSession())

    bridge.stop()

    assert bridge.run_one() is False


def test_the_remote_word_goes_into_the_file_the_show_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Читателя не подделываем: слово забирает та самая единица, которой его забирает
    # идущий показ.
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0),
    )
    bridge = _bridge(session)

    bridge.control(SEEKBY, 90.0)

    assert _SystemChoiceEnvironment().read_command() == "seekby 90"


def test_the_card_is_told_the_new_place_the_second_the_bridge_says_seekby(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Ползунок остаётся там, куда его поставили: опрос следом за командой слышит её.

    Home Assistant переспрашивает состояние сразу после команды
    (``custom_components/torrcast/coordinator.py``, ``async_request_refresh``), а запись
    показа про перемотку ещё не знает: приёмник её только берёт, и закладку сторож
    положит на диск лишь на своём тике (:data:`torrcast.usecases.watch.WATCH_SECONDS`).
    Ответить на том опросе прежним местом - это и есть отскок ползунка назад.
    """
    monkeypatch.setenv(CTL_ENV, str(tmp_path / "torrcast.ctl"))
    session = FakePlaybackSession(
        playing=True,
        play_key="movie:муха",
        shown=PlaybackSnapshot(key="movie:муха", title="Муха", position=60.0, moved=True),
    )
    bridge = _bridge(session)

    assert bridge.state()["position"] == 60.0
    bridge.control(SEEKBY, 900.0)

    assert bridge.state()["position"] == 960.0


def test_a_refused_remote_moves_the_slider_nowhere() -> None:
    """Показа нет - отказ, и никакой защёлки: двигать нечего и незачем."""
    bridge = _bridge(FakePlaybackSession(playing=False))

    with pytest.raises(RefusedError):
        bridge.control(SEEKBY, 900.0)

    assert bridge.state()["position"] is None


_SEARCH_CONFIG = Config(prowlarr_apikey="KEY", tv="10.0.1.7")
_CARS = [
    row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66),
    row("Тачки 2 / Cars 2 (2011) BDRip 1080p | D", "b", size_gb=5.0, seeders=44),
]


def _real_search(answers: dict[str, list[Any]]) -> Callable[..., list[Any]]:
    """Поиск, идущий тем же кругом, что и консоль - только клиент индексеров свой.

    Настоящий :func:`search_circle`, настоящая сборка меню - ничего заново тут не
    придумано, подделан только заход в сеть (:mod:`tests.usecases.discover.world`).
    """

    def search(config: Config, args: Args, progress: Any, profile: Profile = CAUTIOUS) -> list[Any]:
        wire_catalogue()
        client = Indexer(answers=answers)
        return search_circle(
            config,
            args,
            progress,
            profile,
            indexer=lambda *_a, **_k: client,
            passport=lambda *_a, **_k: Origin(),
        )

    return search


def test_the_search_route_lists_the_products_own_plans_with_pick_numbers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Номер и поля идут не от моста, а от того же круга поиска, что и консоль.

    Имена картинок тут не спрашиваются: за ними ходит фоновый поиск постеров
    (:class:`hass.hit_posters.HitPosters`), и в зеркале моста он звонил бы в Википедию.
    """
    monkeypatch.setattr("hass.searching.OFFER", lambda results: results)
    bridge = _bridge(
        FakePlaybackSession(),
        search=_real_search({"тачки": _CARS}),
        settings=lambda: _SEARCH_CONFIG,
    )
    plans = _real_search({"тачки": _CARS})(_SEARCH_CONFIG, Args(query=["тачки"]), Said())
    taken = enter_take(plans, "тачки").number

    results = bridge.search("тачки")

    assert results == [
        {
            "pick": number,
            "key": plan.picture.key,
            "title": plan.picture.title,
            "year": plan.picture.year,
            "kind": plan.picture.kind,
            "original": plan.picture.original or "",
            "default": number == taken,
        }
        for number, plan in enumerate(plans, start=1)
    ]


def test_a_search_refusal_carries_the_products_own_words(_russian_product: None) -> None:
    """409 у поиска не свой: слово - ровно то, что сказал бы отказ круга поиска."""
    bridge = _bridge(
        FakePlaybackSession(), search=_real_search({}), settings=lambda: _SEARCH_CONFIG
    )

    with pytest.raises(RefusedError) as refusal:
        bridge.search("нетакого")

    assert "нетакого" in refusal.value.word
    assert "ничего не нашлось" in refusal.value.word


def test_play_with_a_pick_adds_the_flag_the_cli_understands() -> None:
    """``pick`` из поиска доезжает до показа тем же ``--pick N``, каким его знает CLI."""
    asked: list[list[str]] = []

    def command(argv: Sequence[str] | None) -> int:
        asked.append(list(argv or []))
        return 0

    bridge = _bridge(FakePlaybackSession(), command=command)

    bridge.play("матрица", pick=2)
    bridge.run_one()

    assert asked == [["матрица", "--pick", "2"]]


def test_play_without_a_pick_keeps_the_single_word_call() -> None:
    """Без ``pick`` вызов остаётся ровно тем, каким его знает автовыбор консоли."""
    asked: list[list[str]] = []

    def command(argv: Sequence[str] | None) -> int:
        asked.append(list(argv or []))
        return 0

    bridge = _bridge(FakePlaybackSession(), command=command)

    bridge.play("матрица")
    bridge.run_one()

    assert asked == [["матрица"]]


def test_the_card_is_told_the_picture_of_what_is_playing() -> None:
    """Адрес картинки и её отпечаток уезжают тем же снимком, что и полоса времени."""
    shown = PlaybackSnapshot(key="movie:тачки:2006", title="Тачки", position=5.0, duration=90.0)
    session = FakePlaybackSession(playing=True, play_key=shown.key, shown=shown)
    posters = _Posters(("/api/poster/2f8c", "2f8c"))

    body = _bridge(session, posters=posters).state()

    assert posters.shown == [shown]
    assert body["image"] == "/api/poster/2f8c"
    assert body["image_hash"] == "2f8c"


def test_a_bridge_with_nothing_playing_looks_for_no_picture() -> None:
    """🔴 Снимок прошлого показа остаётся на диске и после его конца.

    Возьмись картинка от него - карточка простаивающего плеера рисовала бы постер кино,
    которое давно кончилось: ровно та ложь, ради которой снимок молчит и об имени, и о
    месте (:func:`hass.payload.payload`).
    """
    ended = PlaybackSnapshot(key="movie:муха:1986", title="Муха", position=60.0, duration=300.0)
    session = FakePlaybackSession(playing=False, shown=ended)
    posters = _Posters(("/api/poster/старое", "старое"))

    body = _bridge(session, posters=posters).state()

    assert posters.shown == [None], f"картинку искали для {posters.shown}"
    assert body["image"] is None


def test_the_stream_address_is_handed_over_as_a_call_and_not_as_a_value() -> None:
    """Адрес нужен одному запасному кадру, а снимок собирается на каждый опрос.

    Отдай его значением - и на каждый опрос карточки (раз в несколько секунд, весь
    фильм) собирался бы адрес раздачи ради картинки, которая давно готова.
    """
    shown = PlaybackSnapshot(key="movie:тачки:2006", title="Тачки", position=5.0, duration=90.0)
    session = FakePlaybackSession(playing=True, play_key=shown.key, shown=shown)
    posters = _Posters()

    _bridge(session, posters=posters).state()

    assert len(posters.streams) == 1
    assert posters.streams[0]() == session.address


def test_the_bridge_serves_the_bytes_it_found_and_nothing_else() -> None:
    """Маршрут картинки отвечает тем, что мост уже нашёл; чужое имя - ничем."""
    posters = _Posters()
    posters.read_as["2f8c"] = (b"\xff\xd8\xff\xe0poster", "image/jpeg")
    bridge = _bridge(FakePlaybackSession(), posters=posters)

    assert bridge.poster("2f8c") == (b"\xff\xd8\xff\xe0poster", "image/jpeg")
    assert bridge.poster("../../etc/passwd") is None


def test_by_default_the_bridge_looks_for_the_picture_itself() -> None:
    """🔴 Источник картинок у моста свой, а не тот двойник, что стоит в пробах.

    Подделка подставляется в каждую проверку выше, и подмени сборка настоящий источник
    пустым - красным не стало бы ничего: карточка осталась бы без постера молча, а
    снимок серва отвечал бы теми же полями, только пустыми.
    """
    made = _bridge(FakePlaybackSession(), posters=OWN_POSTERS)

    assert isinstance(made._posters, Posters)
