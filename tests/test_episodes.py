"""Сериалы без торрента и без systemd: продолжение серии, прыжок, автопереход.

Живьём это проверяется настоящим показом сериала в transient-юните, а здесь —
то же поведение на подставном TorrServer: что юнит доигрывает сериал сам, что CLI
вопросов не задаёт и что конец раздачи именно кончается.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

import pytest

from tests.fakes.show_unit import FakeShowUnit
from torrcast import cli
from torrcast.state import Entry, State
from torrcast.stream import Media, TorrFile
from torrcast.usecases import playback

KEY = "tv:киберпанк-бегущие-по-краю:2022"
#: Три серии раздачи: s1e1 → файл 0, s1e2 → файл 1, s1e3 → файл 2.
EPISODES = [[1, 1, 0], [1, 2, 1], [1, 3, 2]]
MINUTES_24 = 1440.0


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def remember(**fields: object) -> Entry:
    """Положить в состояние сериал с уже выбранной раздачей и дорожкой."""
    defaults: dict[str, Any] = {
        "title": "Киберпанк: Бегущие по краю",
        "magnet": "magnet:?xt=1",
        "kind": "tv",
        "query": "киберпанк",
        "audio": 1,
        "season": 1,
        "episode": 1,
        "episodes": [list(item) for item in EPISODES],
    }
    entry = Entry(**{**defaults, **fields})
    state = State()
    state.put(KEY, entry)
    state.save()
    return entry


def saved() -> Entry:
    entry = State.load().get(KEY)
    assert entry is not None
    return entry


class _FakeTorrServer:
    """TorrServer в объёме, нужном показу: раздача добавляется один раз на magnet."""

    added: ClassVar[list[str]] = []
    dropped: ClassVar[list[str]] = []

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url, self.timeout = url, timeout

    def add(self, magnet: str) -> str:
        _FakeTorrServer.added.append(magnet)
        return "hash"

    def drop(self, torrent_hash: str) -> bool:
        _FakeTorrServer.dropped.append(torrent_hash)
        return True

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        return [TorrFile(i, f"Cyberpunk.S01E0{i + 1}.mkv", 1024**3) for i in range(3)]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"


def _no_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(prompt: str = "") -> str:
        pytest.fail(f"продолжение сериала вопросов не задаёт, а спросили: {prompt}")

    monkeypatch.setattr("builtins.input", refuse)


def _no_unit(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, order: list[str] | None = None
) -> list[str]:
    started: list[str] = []
    monkeypatch.setattr(playback, "start_play_unit", lambda key: started.append(key))
    monkeypatch.setattr(cli, "_await_playing", lambda config, progress, timeout=120.0: None)
    if order is not None:
        show_unit.on_stop = lambda: order.append("stop")
    return started


def test_the_previous_show_is_stopped_before_the_new_record_is_written(
    show_unit: FakeShowUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Прыжок на серию затирался: умирающий юнит по SIGTERM дописывает СВОЮ позицию,
    и запись прыжка, сделанная до `systemctl stop`, пропадала — играла старая серия.
    Поэтому сначала гасим прошлый показ, и только потом пишем, что играть дальше.
    """
    remember(episode=1, pos=600.0, dur=MINUTES_24)
    order: list[str] = []
    _no_questions(monkeypatch)
    _no_unit(show_unit, monkeypatch, order)
    monkeypatch.setattr(State, "save", lambda self: order.append("save"))

    assert cli.main(["киберпанк", "s1e3"]) == 0

    assert order == ["stop", "save"]


def test_the_unit_plays_the_whole_release_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    """Автопереход: серия дошла до порога 95 % — юнит сам берёт следующий файл
    раздачи, без участия CLI. Раздача кончилась — цикл выходит, юнит гаснет чисто.
    """
    remember(dur=MINUTES_24)
    _FakeTorrServer.added, _FakeTorrServer.dropped = [], []
    played: list[tuple[str, int]] = []
    receivers: list[Any] = []
    tv = object()

    def play(
        config: Any,
        source: str,
        audio: int,
        about: str,
        clock: Any,
        watch: Any = None,
        duration: float = 0.0,
        receiver: Any = None,
        codec: str = "",
        depth: int = 0,
        follow: Any = None,
        supply: Any = None,
        profile: Any = None,
        **rest: Any,
    ) -> int:
        played.append((about, int(source.rsplit("/", 1)[-1])))
        receivers.append(receiver)
        watch.see(watch.entry.dur)
        watch.close()  # серия доиграна до конца - конец сеанса берёт следующую
        return 0

    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(
        cli, "probe", lambda url, timeout=90.0, alive=None: Media(MINUTES_24, (), "h264")
    )
    monkeypatch.setattr(cli, "make_receiver", lambda kind, address, cert, profile=None: tv)
    monkeypatch.setattr(cli, "_play", play)

    assert cli._cmd_worker(KEY) == 0

    assert receivers == [tv, tv, tv], (
        "приёмник один на весь юнит - второй сендер гасит показ на стыке серий"
    )
    assert [about for about, _ in played] == [
        "Киберпанк: Бегущие по краю s1e1",
        "Киберпанк: Бегущие по краю s1e2",
        "Киберпанк: Бегущие по краю s1e3",
    ]
    assert [index for _, index in played] == [0, 1, 2], "каждой серии - свой файл раздачи"
    assert _FakeTorrServer.added == ["magnet:?xt=1"], "раздача одна: заново её не добавляем"
    assert _FakeTorrServer.dropped == ["hash"], "и на конце показа она убрана - хозяин кончился"
    assert saved().done and saved().label == "s1e3", "конец раздачи отмечен в состоянии"


def test_the_next_episode_learns_its_own_duration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Порог 95 % считается от длительности серии, а её у следующей серии ещё нет:
    юнит читает её из потока сам, иначе «досмотрено» наступило бы мгновенно.
    """
    remember(dur=MINUTES_24, depth=8, frame=1080)  # у первой серии паспорт полный
    probed: list[str] = []

    def probe(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        probed.append(url)
        return Media(MINUTES_24 + len(probed), (), "h264", pix_fmt="yuv420p")

    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(cli, "probe", probe)
    monkeypatch.setattr(cli, "make_receiver", lambda kind, address, cert, profile=None: None)
    monkeypatch.setattr(
        cli,
        "_play",
        lambda config, source, audio, about, clock, watch=None, **rest: (
            watch.see(watch.entry.dur),
            watch.close(),
            0,
        )[2],
    )

    assert cli._cmd_worker(KEY) == 0

    assert len(probed) == 2, "у первой серии длительность уже была, у двух следующих - нет"


def test_a_record_from_before_the_ten_bit_era_asks_the_passport_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Запись прежней версии глубины цвета не несёт - и молчит она как «восемь бит».

    Это не мелочь учёта: на десятибитном H.264 такое молчание означает «уезжай копией», а
    копию приёмник не декодирует - доигрывает буфер и встаёт (TC-164). Поэтому глубина
    добирается одним ffprobe при первом же продолжении и остаётся в записи навсегда.
    """
    remember(dur=MINUTES_24, codec="h264")  # depth не проставлен - запись прежней версии
    probed: list[str] = []
    seen: list[int] = []

    def probe(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        probed.append(url)
        return Media(MINUTES_24, (), "h264", profile="High 10", pix_fmt="yuv420p10le")

    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(cli, "probe", probe)
    monkeypatch.setattr(cli, "make_receiver", lambda kind, address, cert, profile=None: None)

    def play(
        config: Any, source: str, audio: int, about: str, clock: Any, watch: Any = None, **rest: Any
    ) -> int:
        seen.append(int(rest.get("depth") or 0))
        watch.see(watch.entry.dur)
        watch.close()
        return 0

    monkeypatch.setattr(cli, "_play", play)

    assert cli._cmd_worker(KEY) == 0

    assert seen[0] == 10, "показ обязан узнать глубину, а не решать по одному имени кодека"
    assert saved().depth == 10, "узнанное осталось в записи - второй раз спрашивать незачем"
    assert probed[:1] == ["http://ts/hash/0"], "и спрошено это ровно один раз на серию"


def test_a_record_from_before_the_frame_era_asks_the_passport_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 TC-251. Запись прежней версии кадра не несёт - и молчит она как «1080p».

    Молчание читается :func:`torrcast.recode.level_for` как «4.1», а на 4К это враньё в
    поток: у 2160p 32400 макроблоков против потолка 8192. Поэтому кадр добирается тем же
    одним ffprobe, что и глубина цвета, при первом же продолжении - и остаётся в записи.
    """
    remember(dur=MINUTES_24, codec="h264", depth=8)  # frame не проставлен - прежняя версия
    probed: list[str] = []
    seen: list[int] = []

    def probe(url: str, timeout: float = 90.0, alive: object = None) -> Media:
        probed.append(url)
        return Media(MINUTES_24, (), "h264", height=2160, width=3840, pix_fmt="yuv420p")

    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(cli, "probe", probe)
    monkeypatch.setattr(cli, "make_receiver", lambda kind, address, cert, profile=None: None)

    def play(
        config: Any, source: str, audio: int, about: str, clock: Any, watch: Any = None, **rest: Any
    ) -> int:
        seen.append(int(rest.get("frame") or 0))
        watch.see(watch.entry.dur)
        watch.close()
        return 0

    monkeypatch.setattr(cli, "_play", play)

    assert cli._cmd_worker(KEY) == 0

    assert seen[0] == 2160, "показ обязан узнать кадр, а не писать в поток «4.1» на 4К"
    assert saved().frame == 2160, "узнанное осталось в записи - второй раз спрашивать незачем"
    assert probed[:1] == ["http://ts/hash/0"], "и спрошено это ровно один раз на серию"


def test_the_unit_signs_its_torrent_in_the_state_and_unsigns_it_on_the_way_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Хэш раздачи знал только живой процесс: убитый SIGKILL юнит уносил его с собой, а
    раздача оставалась в TorrServer навсегда - и убрать её было нечем.

    Поэтому хэш пишется в состояние ровно тогда, когда раздача поднята, и снимается
    ровно тогда, когда она убрана. Внутри показа отметка обязана пережить и сторожа
    позиции (он кладёт запись на диск каждые несколько секунд), и стык серий: раздача
    одна на всю раздачу.
    """
    remember(dur=MINUTES_24, depth=8)
    _FakeTorrServer.added, _FakeTorrServer.dropped = [], []
    signed: list[str] = []

    def play(
        config: Any, source: str, audio: int, about: str, clock: Any, watch: Any = None, **rest: Any
    ) -> int:
        watch.see(watch.entry.dur)
        watch.close()  # заодно и сторож кладёт запись на диск
        entry = State.load().get(KEY)
        signed.append(entry.torrent if entry else "")
        return 0

    monkeypatch.setattr(cli, "TorrServer", _FakeTorrServer)
    monkeypatch.setattr(cli, "probe", lambda url, timeout=90.0, alive=None: Media(MINUTES_24, ()))
    monkeypatch.setattr(cli, "make_receiver", lambda kind, address, cert, profile=None: None)
    monkeypatch.setattr(cli, "_play", play)

    assert cli._cmd_worker(KEY) == 0

    assert signed == ["hash", "hash", "hash"], "пока показ идёт, хозяин раздачи назван"
    assert _FakeTorrServer.dropped == ["hash"], "раздача убрана на выходе, как и раньше"
    assert saved().torrent == "", "убрана - и отметки о ней больше нет"


def test_a_series_continues_the_right_episode_from_the_right_place(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast киберпанк` без аргументов: продолжает недосмотренную серию с позиции,
    вопросов не задаёт вовсе — релиз, дорожка и список серий уже выбраны.
    """
    remember(episode=2, file_idx=1, pos=300.0, dur=MINUTES_24)
    _no_questions(monkeypatch)
    started = _no_unit(show_unit, monkeypatch)

    assert cli.main(["киберпанк"]) == 0

    printed = capsys.readouterr().out
    assert "s1e2" in printed and "с 0:05:00" in printed
    assert "ищу" not in printed, "продолжение не ходит в Prowlarr"
    assert started == [KEY]
    assert saved().pos == 300.0 and saved().file_idx == 1


def test_a_watched_episode_is_followed_by_the_next_one_without_questions(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Серия досмотрена до порога — `cast киберпанк` играет следующую с нуля."""
    remember(episode=3, file_idx=2, pos=0.0, dur=0.0)  # так выглядит запись после стыка
    _no_questions(monkeypatch)
    _no_unit(show_unit, monkeypatch)

    assert cli.main(["киберпанк"]) == 0

    assert "s1e3" in capsys.readouterr().out


def test_an_episode_stopped_at_96_percent_starts_the_next_one(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    remember(episode=2, file_idx=1, pos=1382.4, dur=MINUTES_24)
    _no_questions(monkeypatch)
    _no_unit(show_unit, monkeypatch)

    assert cli.main(["киберпанк"]) == 0

    said = capsys.readouterr().out
    assert "s1e2 досмотрено" in said and "играю s1e3" in said
    assert "с 0:23:02" not in said
    assert saved().episode == 3 and saved().file_idx == 2 and saved().pos == 0.0


def test_the_last_episode_does_not_promise_an_automatic_restart(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    remember(episode=3, file_idx=2, pos=1382.4, dur=MINUTES_24)
    asked: list[str] = []

    def answer(prompt: str = "") -> str:
        asked.append(prompt)
        return "нет"

    monkeypatch.setattr("builtins.input", answer)

    assert cli.main(["киберпанк", "--dry"]) == 0

    said = capsys.readouterr().out
    assert said.count("была последней в раздаче") == 1
    assert "играю с начала" not in said
    assert asked == ["Смотреть сначала? [Да/нет]: "]
    assert saved().done and saved().episode == 3 and saved().pos == 0.0


def test_a_named_episode_is_not_shadowed_by_the_watched_bookkeeping(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """🔴 Названная серия сильнее бухгалтерии досмотра: закладка стоит на s1e2 за долей,
    но человек попросил s1e1 - и обещать ему s1e3 нельзя. Пока бухгалтерия шла раньше
    прыжка, зритель получал две строки подряд: «играю s1e3» и следом «играю s1e1».
    """
    remember(episode=2, file_idx=1, pos=1382.4, dur=MINUTES_24)
    _no_questions(monkeypatch)
    _no_unit(show_unit, monkeypatch)

    assert cli.main(["киберпанк", "s1e1"]) == 0

    said = capsys.readouterr().out
    assert "досмотрено" not in said and "s1e3" not in said
    assert saved().episode == 1 and saved().file_idx == 0 and saved().pos == 0.0


def test_an_explicit_episode_jumps_inside_the_cached_release(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast киберпанк s1e3`: прыжок по кэшу раздачи — ни поиска, ни вопросов."""
    remember(episode=1, pos=600.0, dur=MINUTES_24)
    _no_questions(monkeypatch)
    _no_unit(show_unit, monkeypatch)

    assert cli.main(["киберпанк", "s1e3"]) == 0

    assert "s1e3" in capsys.readouterr().out
    assert (saved().episode, saved().file_idx, saved().pos) == (3, 2, 0.0)


def test_an_episode_outside_the_release_goes_looking_for_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast киберпанк s2e5`, а в раздаче только первый сезон: молчаливой подмены нет —
    цепочка идёт искать релиз нужного сезона (тут упирается в ненастроенный Prowlarr).
    """
    remember(episode=1, pos=600.0, dur=MINUTES_24)
    monkeypatch.setattr(playback, "start_play_unit", lambda key: pytest.fail("играть нечего"))

    assert cli.main(["киберпанк", "s2e5"]) == 2

    assert "Prowlarr" in capsys.readouterr().err
    assert saved().episode == 1, "запись не тронута: серию не нашли"


def test_the_end_of_the_release_is_the_end(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Раздача досмотрена: следующая серия не выдумывается. Ответ «нет» — просто выходим."""
    remember(episode=3, file_idx=2, done=True, dur=MINUTES_24)
    monkeypatch.setattr("builtins.input", lambda prompt="": "нет")
    monkeypatch.setattr(playback, "start_play_unit", lambda key: pytest.fail("играть нечего"))

    assert cli.main(["киберпанк"]) == 0

    assert "s1e3 была последней в раздаче" in capsys.readouterr().out


def test_the_finished_release_can_be_started_over(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """…а Enter на том же вопросе начинает раздачу сначала: выбор релиза не повторяется."""
    remember(episode=3, file_idx=2, done=True, dur=MINUTES_24)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    _no_unit(show_unit, monkeypatch)

    assert cli.main(["киберпанк"]) == 0

    assert "s1e1" in capsys.readouterr().out
    assert (saved().episode, saved().file_idx, saved().done) == (1, 0, False)


def test_status_names_the_episode(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast status` о сериале говорит серией, а не только названием."""
    remember(episode=2, file_idx=1, pos=310.0, dur=MINUTES_24)
    show_unit.alive = True
    show_unit.playing = KEY

    assert cli.main(["status"]) == 0

    assert "играю «Киберпанк: Бегущие по краю» s1e2 - 0:05:10 / 0:24:00" in capsys.readouterr().out
