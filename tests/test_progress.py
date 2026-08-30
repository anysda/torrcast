"""Сторож, порог «досмотрено», resume и управление показом.

Живьём это проверяется настоящим показом в transient-юните, а здесь — то же
поведение без торрента и без systemd: переходы состояния и ветки CLI.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from tests.fakes import composition
from tests.fakes.show_unit import FakeShowUnit
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.filesystem.state.state import State
from torrcast.cli.main import main
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.torrent_hash import _torrent_hash
from torrcast.usecases.torrents import _release_orphans
from torrcast.usecases.watch import Watch

KEY = "movie:моана-2:2024"


@pytest.fixture(autouse=True)
def _isolate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Ни /var/lib/torrcast, ни /etc/torrcast, ни живых юнитов."""
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))


def saved(key: str = KEY) -> Entry:
    entry = State.load().get(key)
    assert entry is not None
    return entry


def remember(**fields: object) -> Entry:
    """Положить в состояние недосмотренный фильм."""
    fields = {"magnet": "magnet:?xt=1", **fields}
    entry = Entry(title="Моана 2", query="моана-2", **fields)  # type: ignore[arg-type]
    state = State()
    state.put(KEY, entry)
    state.save()
    return entry


def test_watchdog_writes_position_not_more_often_than_the_interval() -> None:
    """Раз в 10 с: между тиками состояние не переписывается на каждый опрос."""
    entry = remember(pos=0.0, dur=5978.0)
    watch = Watch(key=KEY, entry=entry, every=3600.0)

    watch.see(120.0)  # интервал не вышел - на диске по-прежнему ноль

    assert saved().pos == 0.0
    watch.every = 0.0
    watch.see(130.0)
    assert saved().pos == 130.0
    assert saved().updated, "метка времени обязательна"


def test_watchdog_takes_the_position_as_absolute_film_time() -> None:
    """Позиция приёмника — абсолютное время фильма, пересчитывать нечего.

    Манифест описывает весь фильм, а ``-copyts`` оставляет в сегментах исходные метки,
    поэтому приёмник считает от начала фильма, с какого бы места ни шла упаковка. Ноль —
    единственное, что игнорируется: так приёмник отвечает, пока ещё не начал считать, и
    затирать им честную позицию нельзя.
    """
    entry = remember(pos=2400.0, dur=5978.0)
    watch = Watch(key=KEY, entry=entry, every=0.0)

    watch.see(2465.0)
    assert saved().pos == 2465.0

    watch.see(0.0)
    assert saved().pos == 2465.0, "нулём с непрогретого приёмника позицию не теряем"


def test_watchdog_marks_the_movie_watched_only_at_the_end_of_the_show() -> None:
    """Пометка «досмотрено» приезжает концом сеанса, а не долей длительности.

    Пока картина играет, сторож пишет только позицию: ни 95 %, ни «минус секунда» показ
    больше никуда не уводят. Конец сеанса ставит пометку и сбрасывает позицию, а повторные
    тики её не воскрешают - иначе следующий `cast` спросил бы «продолжить?» о досмотренном.
    """
    entry = remember(pos=0.0, dur=1000.0)
    watch = Watch(key=KEY, entry=entry, every=0.0)

    watch.see(950.0)
    assert not saved().done and saved().pos == 950.0, "95 % - это ещё картина, а не титры"

    watch.see(999.2)
    assert not saved().done and saved().pos == 999.2, "и последняя секунда - тоже ещё картина"

    watch.close()
    assert saved().done and saved().pos == 0.0

    watch.see(1000.0)
    assert saved().done and saved().pos == 0.0


def test_resume_is_silent_and_starts_from_the_saved_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Продолжаем молча; релиз и дорожка из состояния, поиска нет."""
    remember(pos=2467.0, dur=5978.0, audio=1)
    started: list[str] = []
    asked: list[str] = []

    def ask(prompt: str = "") -> str:
        asked.append(prompt)
        return ""

    composition.use_start_unit(monkeypatch, started.append)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )
    monkeypatch.setattr("builtins.input", ask)

    assert main(["моана", "2"]) == 0

    printed = capsys.readouterr().out
    assert asked == []
    assert "- on TV" in printed
    assert "ищу" not in printed, "resume не ходит в Prowlarr"
    assert started == [KEY]
    assert saved().pos == 2467.0 and saved().audio == 1


def test_new_keeps_the_release_but_drops_the_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--new`` - та же раздача и дорожка, позиция ноль."""
    remember(pos=2467.0, dur=5978.0, audio=1)
    composition.use_start_unit(monkeypatch, lambda key: None)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("меню не нужно"))

    assert main(["моана", "2", "--new"]) == 0
    assert saved().pos == 0.0 and saved().audio == 1


def test_new_restarts_the_recorded_episode_not_the_series(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Сериал остаётся на записанной серии, меняется только её позиция."""
    key = "tv:сериал:2024"
    state = State()
    state.put(
        key,
        Entry(
            title="Сериал",
            magnet="magnet:?xt=series",
            kind="tv",
            file_idx=9,
            audio=2,
            pos=1234.0,
            dur=2400.0,
            query="сериал",
            season=2,
            episode=5,
            episodes=[[1, 1, 1], [2, 5, 9], [2, 6, 10]],
        ),
    )
    state.save()
    composition.use_start_unit(monkeypatch, lambda key: None)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": pytest.fail("меню не нужно"))

    assert main(["сериал", "--new"]) == 0

    restarted = saved(key)
    episode = (restarted.season, restarted.episode, restarted.file_idx, restarted.pos)
    assert episode == (2, 5, 9, 0.0)
    assert (restarted.magnet, restarted.audio) == ("magnet:?xt=series", 2)


def test_new_jumps_to_the_named_episode_in_the_saved_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Явно названная серия сильнее записанной, но раздача остаётся прежней."""
    key = "tv:сериал:2024"
    state = State()
    state.put(
        key,
        Entry(
            title="Сериал",
            magnet="magnet:?xt=series",
            kind="tv",
            file_idx=9,
            pos=1234.0,
            query="сериал",
            season=2,
            episode=5,
            episodes=[[2, 5, 9], [2, 6, 10]],
        ),
    )
    state.save()
    composition.use_start_unit(monkeypatch, lambda key: None)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )

    assert main(["сериал", "s2e6", "--new"]) == 0

    restarted = saved(key)
    assert (restarted.season, restarted.episode, restarted.file_idx, restarted.pos) == (
        2,
        6,
        10,
        0.0,
    )
    assert restarted.magnet == "magnet:?xt=series"


def test_watched_movie_restarts_without_a_question(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    remember(pos=950.0, dur=1000.0)
    started: list[str] = []
    asked: list[str] = []

    def ask(prompt: str = "") -> str:
        asked.append(prompt)
        return ""

    composition.use_start_unit(monkeypatch, started.append)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )
    monkeypatch.setattr("builtins.input", ask)

    assert main(["моана", "2"]) == 0
    assert started == [KEY]
    assert asked == []
    assert saved().pos == 0.0 and not saved().done
    said = capsys.readouterr().out
    line = phrase(
        "account_watched.done",
        title="Моана 2",
        what="",
        stopped="0:15:50",
        dur="0:16:40",
        decision=phrase("account_watched.from_start"),
    )
    assert said.count(line) == 1


def test_dry_resume_does_not_touch_the_unit(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    remember(pos=2467.0, dur=5978.0)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    composition.use_start_unit(monkeypatch, lambda key: pytest.fail("--dry юнитов не поднимает"))

    assert main(["моана", "2", "--dry"]) == 0
    assert "not casting" in capsys.readouterr().out
    assert show_unit.stops == [], "--dry не поднимает юнит, но и чужой показ не гасит"


def test_status_is_honest_when_nothing_plays(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Юнита нет — «ничего не играет», но недосмотренное кино назвать не грех."""
    remember(pos=2467.0, dur=5978.0)
    show_unit.alive = False

    assert main(["status"]) == 0

    printed = capsys.readouterr().out
    assert printed.startswith(phrase("status.nothing_playing"))
    marker = "DURATION-MARKER"
    head = phrase(
        "status.last_resumable", title="Моана 2", pos="0:41:07", duration=marker
    ).split(marker)[0]
    assert head in printed


def test_status_tells_about_a_show_that_died_without_a_single_frame(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Показ умер, не показав ничего, - `cast status` обязан сказать об этом.

    🔴 Замер 16-08-2026 на живой приставке: показ не дал ни кадра, юнит вышел, и статус
    отвечал «ничего не играет» - ровно то же, что и после спокойного конца фильма. На
    стыке серий консоли рядом нет вовсе, и это была единственная дверь к правде: позиции
    у такого показа нет (ноль), «последнее» про него не печатается, а журнал юнита ушёл
    вместе с юнитом. Отметку темноты снимает только следующий запуск - до тех пор она и
    есть ответ на вопрос «почему экран чёрный».
    """
    remember(pos=0.0, dur=5978.0, dark=time.time(), dark_why="приёмник бросил показ")
    show_unit.alive = False

    assert main(["status"]) == 0

    printed = capsys.readouterr().out
    assert phrase(
        "status.torn", what="«Моана 2»", was=phrase("status.no_frame"), reason="приёмник бросил показ"
    ) in printed
    assert phrase("status.nothing_playing") not in printed, (
        "молчаливого «всё в порядке» тут быть не должно"
    )


def test_status_shows_what_is_playing_and_from_where(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Живой юнит: что играет, позиция/длительность, источник."""
    remember(pos=2467.0, dur=5978.0, audio=1, file_idx=2)
    show_unit.alive = True

    assert main(["status"]) == 0

    printed = capsys.readouterr().out
    assert phrase("status.playing", what="«Моана 2»", pos="0:41:07", duration="1:39:38") in printed
    assert KEY in printed and "file #2" in printed and "track 2" in printed


def test_status_does_not_call_a_black_screen_a_show(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Юнит жив, а картинки нет - статус говорит про темноту, а не «играю».

    Живой юнит доказывает, что показ заведён, и только это: он нарочно переживает смерть
    источника, чтобы поднять показ, когда тот вернётся. Замер на живом стенде: с мёртвым
    источником юнит жил 902 с, и все эти минуты статус отвечал «играю» - человек смотрел в
    чёрный экран, которому инструмент выдавал справку о здоровье.
    """
    remember(pos=2467.0, dur=5978.0, dark=time.time() - 200.0, dark_why="TorrServer не отвечает")
    show_unit.alive = True

    assert main(["status"]) == 0

    printed = capsys.readouterr().out
    assert "playing" not in printed, "чёрный экран назван показом"
    assert phrase("status.dark", what="«Моана 2»", pos="0:41:07", duration="1:39:38") in printed
    darkness = phrase("status.darkness_for", hms="0:03:20")
    assert phrase("status.dark_wait", darkness=darkness, reason="TorrServer не отвечает") in printed


def test_status_names_the_unit_key_not_the_freshest_record(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Играющее определяется по ``--description`` юнита: рядом мог писать другой запуск,
    и «самая свежая запись» назвала бы чужую картину.
    """
    remember(pos=660.0, dur=5978.0)
    state = State.load()  # запись свежее, но она НЕ играет
    state.put("movie:чужое-кино:2020", Entry(title="Чужое кино", magnet="magnet:?xt=2", pos=10.0))
    state.save()
    show_unit.alive = True
    show_unit.playing = KEY

    assert main(["status"]) == 0

    printed = capsys.readouterr().out
    assert "«Моана 2»" in printed and "Чужое кино" not in printed


def test_stop_reports_the_playing_record_and_asks_the_unit_before_killing_it(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """У мёртвого юнита описания уже не спросишь — ключ снимается до `systemctl stop`."""
    remember(pos=660.0, dur=5978.0)
    order: list[str] = []

    def ask_the_unit() -> str:
        order.append("key")
        return KEY

    show_unit.alive = True
    show_unit.on_key = ask_the_unit
    show_unit.on_stop = lambda: order.append("stop")

    assert main(["stop"]) == 0

    assert order == ["key", "stop"]
    assert "«Моана 2»" in capsys.readouterr().out


def test_stop_kills_the_unit_and_reports_the_fixed_position(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast stop`: юнит гасится, позицию в state дописывает сам юнит по SIGTERM."""
    remember(pos=660.0, dur=5978.0)
    stopped: list[bool] = []
    show_unit.alive = True
    show_unit.on_stop = lambda: stopped.append(True)

    assert main(["stop"]) == 0

    assert stopped == [True]
    line = phrase("stop.stopped", title="Моана 2", pos="0:11:00", duration="1:39:38")
    assert line in capsys.readouterr().out


def test_stop_without_playback_says_so(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    show_unit.alive = False

    assert main(["stop"]) == 0
    assert capsys.readouterr().out.strip() == phrase("stop.nothing_playing")


#: Хэш и магнит остановленной картины: снос идёт по хэшу ИЗ МАГНИТА, а не по списку.
HASH = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"
PLAYED = f"magnet:?xt=urn:btih:{HASH.upper()}&dn=Moana+2&tr=udp%3A%2F%2Ftracker%3A1337"


class _Torrents:
    """TorrServer в объёме уборки: что у него просили снять, просили ли вообще и
    дозвонились ли. Молчащая служба ничего не убирает и отвечает об этом (``drop`` -
    ложь): «убрал» и «не дозвонился» - разные события, и различает их только ответ.
    """

    def __init__(self, up: bool = True) -> None:
        self.dropped: list[str] = []
        self.up = up

    def __call__(self, url: str, timeout: float = 30.0) -> _Torrents:
        return self

    def add(self, magnet: str) -> str:
        """Пусть служба молчит: это штатная ветка, и на уборку она не влияет."""
        raise InfraError("TorrServer не отвечает")

    def drop(self, torrent_hash: str) -> bool:
        if not self.up:
            return False
        self.dropped.append(torrent_hash)
        return True


def test_stop_takes_the_torrent_down_with_the_show(
    show_unit: FakeShowUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 `cast stop` гасил юнит, а раздача оставалась жить в TorrServer до его перезапуска.

    Раздачу за собой убирает сам юнит, но умереть он мог и не по-людски (SIGKILL по
    таймауту, паника, перезагрузка), а раздача переживает свой процесс. Поэтому тот же
    хэш сносится ещё раз отсюда - и берётся он из МАГНИТА остановленной записи: списка
    службы не различает владельцев, а сносить по списку значило бы сносить чужое.
    """
    remember(pos=660.0, dur=5978.0, magnet=PLAYED)
    torrents = _Torrents()
    show_unit.alive = True
    show_unit.playing = KEY
    composition.use_engines(monkeypatch, torrents)

    assert main(["stop"]) == 0

    assert torrents.dropped == [HASH], "снят ровно свой хэш, в нижнем регистре и один раз"


def test_stop_with_nothing_playing_touches_no_torrent(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ничего не играло - ничего и не сносим: ту же раздачу может прямо сейчас греть
    чужой ход, и «на всякий случай» её убирать нельзя.
    """
    remember(pos=660.0, dur=5978.0, magnet=PLAYED)
    torrents = _Torrents()
    show_unit.alive = False
    show_unit.playing = ""
    composition.use_engines(monkeypatch, torrents)

    assert main(["stop"]) == 0

    assert torrents.dropped == []


#: Хэш раздачи, которую поднял умерший юнит: он записан в состоянии и больше нигде.
ORPHAN = "aa11bb22cc33dd44ee55ff6677889900aabbccdd"


def test_the_next_cast_takes_down_the_torrent_of_a_killed_unit(
    show_unit: FakeShowUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Юнит, убитый SIGKILL, оставлял раздачу в TorrServer навсегда: хэш знал только
    мёртвый процесс, а список службы не различает владельцев.

    Теперь хэш лежит в состоянии рядом с позицией, и следующий ``cast``, увидев запись
    без живого юнита, убирает раздачу по этому явному хэшу - и только по нему. Повторный
    запуск на убранной раздаче не падает: сноса больше нет, потому что нет и записи.
    """
    remember(pos=2467.0, dur=5978.0, torrent=ORPHAN)
    torrents = _Torrents()
    composition.use_engines(monkeypatch, torrents)
    show_unit.alive = False
    composition.use_start_unit(monkeypatch, lambda key: None)
    composition.use_await_playing(
        monkeypatch, lambda config, progress, timeout=120.0, start=0.0: None
    )
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    assert main(["моана", "2"]) == 0

    assert torrents.dropped == [ORPHAN], "убрано ровно записанное, по явному хэшу"
    assert saved().torrent == "", "сирота убрана - и отметка о ней снята"

    torrents.dropped.clear()
    assert main(["моана", "2"]) == 0
    assert torrents.dropped == [], "второй раз убирать нечего, и это не ошибка"


def test_a_live_show_keeps_its_torrent(
    show_unit: FakeShowUnit, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Запись есть, а юнит ЖИВ - раздача его: трогать её нельзя, иначе показ на экране
    останется без источника. Мёртвым хозяин считается по живости процесса, а не по факту
    записи.
    """
    remember(pos=2467.0, dur=5978.0, torrent=ORPHAN)
    torrents = _Torrents()
    composition.use_engines(monkeypatch, torrents)
    show_unit.alive = True

    _release_orphans(load_config())

    assert torrents.dropped == []
    assert saved().torrent == ORPHAN, "хозяин жив - отметка остаётся его"


def test_a_torrent_the_service_did_not_take_down_is_not_forgotten(
    show_unit: FakeShowUnit,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 Молчание службы - не уборка, а хэш забывался всё равно, и раздача становилась
    вечной.

    Замер на стенде: показ кончился при лежащей службе раздач, снос до неё не доехал -
    и отметка о раздаче из состояния всё равно исчезла. Раздача при этом переживает свой
    процесс и живёт в службе до её перезапуска, а снести её больше нечем: хэш не знает
    никто. Забывать его можно только вместе с раздачей.
    """
    remember(pos=2467.0, dur=5978.0, torrent=ORPHAN)
    torrents = _Torrents(up=False)
    composition.use_engines(monkeypatch, torrents)
    show_unit.alive = False

    _release_orphans(load_config())

    assert torrents.dropped == [], "службы нет - убирать было некому"
    assert saved().torrent == ORPHAN, "раздача жива, и хэш - единственное, чем её снести"

    torrents.up = True
    _release_orphans(load_config())

    assert torrents.dropped == [ORPHAN], "служба вернулась - сироту убрал следующий запуск"
    assert saved().torrent == "", "вот теперь раздачи нет, и записи о ней тоже"


class _Answer:
    """Ответ службы на снос: код есть, тела нет. Ровно так отвечает живой TorrServer."""

    status_code = 200

    def raise_for_status(self) -> None:
        pass

    def json(self) -> object:
        raise ValueError("нечего разбирать")


class _Answering:
    def post(self, url: str, json: object = None, timeout: float = 0.0) -> _Answer:
        return _Answer()


def test_the_service_answers_whether_it_took_the_torrent_down() -> None:
    """Ответ на снос - про службу, а не про раздачу: без него уборку не отличить от тишины.

    Раздачи, которой служба не знает, снос стоит одного обычного «убрал» (замер на живой
    службе), так что повторять его безопасно. Значит осечка тут означает ровно одно -
    службы сейчас нет; исключением она по-прежнему не становится, показ на выходе ждать
    её не вправе.

    🔴 И тело у этого ответа пустое (замер на живой службе). Пока пустой ответ считался
    «служба вернула не JSON», снос НИКОГДА не выглядел удавшимся - даже когда раздачу
    честно убрали.
    """
    from torrcast.adapters.torrserver.torr_server import TorrServer

    assert TorrServer("http://127.0.0.1:1").drop(ORPHAN) is False, "службы нет - и уборки нет"

    served = TorrServer("http://127.0.0.1:1")
    served._session = _Answering()  # type: ignore[assignment]
    assert served.drop(ORPHAN) is True, "пустой ответ - это ответ, а не поломка"


def test_a_magnet_gives_up_its_hash_without_asking_anyone() -> None:
    """Хэш - часть самого магнита, и знать его можно, не поднимая ничего.

    Разбирается только сорокознаковая hex-форма: base32 - другая запись того же хэша,
    TorrServer знает раздачу по hex, и снос «похожей строки» был бы сносом наугад.
    """
    assert _torrent_hash(PLAYED) == HASH
    assert _torrent_hash("magnet:?xt=urn:btih:MFRGGZDFMZTWQ2LKNNWG23TP&dn=x") == ""
    assert _torrent_hash("magnet:?xt=1") == "" and _torrent_hash("") == ""
