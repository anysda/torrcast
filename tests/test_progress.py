"""Этап 3: сторож, порог «досмотрено», resume и управление показом (§2.3, §2.5, §4).

Живая приёмка идёт на «Моане 2» в transient-юните (docs/stage3.md), а здесь — то же
поведение без торрента и без systemd: переходы состояния и ветки CLI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast import cli
from torrcast.state import Entry, State
from torrcast.stream import unit_active, unit_why

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
    entry = Entry(title="Моана 2", magnet="magnet:?xt=1", query="моана-2", **fields)  # type: ignore[arg-type]
    state = State()
    state.put(KEY, entry)
    state.save()
    return entry


def test_watchdog_writes_position_not_more_often_than_the_interval() -> None:
    """Раз в 10 с (§3): между тиками состояние не переписывается на каждый опрос."""
    entry = remember(pos=0.0, dur=5978.0)
    watch = cli.Watch(key=KEY, entry=entry, every=3600.0)

    watch.see(120.0)  # интервал не вышел — на диске по-прежнему ноль

    assert saved().pos == 0.0
    watch.every = 0.0
    watch.see(130.0)
    assert saved().pos == 130.0
    assert saved().updated, "метка времени обязательна (§4)"


def test_watchdog_counts_position_from_the_resume_offset() -> None:
    """Приёмник считает время от начала своего потока, а после resume поток начинается
    с ``-ss offset`` — в состояние обязана лечь абсолютная позиция в фильме.
    """
    entry = remember(pos=2400.0, dur=5978.0)
    watch = cli.Watch(key=KEY, entry=entry, offset=2400.0, every=0.0)

    watch.see(65.0)

    assert saved().pos == 2465.0


def test_watchdog_marks_the_movie_watched_at_95_percent() -> None:
    """Порог 95 % (§2.4): запись «досмотрено», позиция сброшена, повторные тики её не
    воскрешают — иначе следующий `cast` спросил бы «продолжить?» о досмотренном фильме.
    """
    entry = remember(pos=0.0, dur=1000.0)
    watch = cli.Watch(key=KEY, entry=entry, every=0.0)

    watch.see(949.0)
    assert not saved().done and saved().pos == 949.0

    watch.see(950.0)
    assert saved().done and saved().pos == 0.0

    watch.see(960.0)
    assert saved().done and saved().pos == 0.0


def test_resume_asks_once_and_starts_from_the_saved_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """§2.3: один вопрос, Enter — продолжаем; релиз и дорожка из состояния, поиска нет."""
    remember(pos=2467.0, dur=5978.0, audio=1)
    started: list[str] = []
    asked: list[str] = []

    def ask(prompt: str = "") -> str:
        asked.append(prompt)
        return ""

    monkeypatch.setattr(cli, "start_play_unit", lambda key: started.append(key))
    monkeypatch.setattr(cli, "_await_playing", lambda config, timeout=120.0: None)
    monkeypatch.setattr("builtins.input", ask)

    assert cli.main(["моана", "2"]) == 0

    printed = capsys.readouterr().out
    assert asked == ["«Моана 2» остановились на 0:41:07. Продолжить? [Да/сначала]: "]
    assert "→ ТВ" in printed
    assert "ищу" not in printed, "resume не ходит в Prowlarr (§3.1)"
    assert started == [KEY]
    assert saved().pos == 2467.0 and saved().audio == 1


def test_resume_from_the_beginning_keeps_the_release_but_drops_the_position(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«сначала» — та же раздача и дорожка, позиция ноль (§2.3)."""
    remember(pos=2467.0, dur=5978.0, audio=1)
    monkeypatch.setattr(cli, "start_play_unit", lambda key: None)
    monkeypatch.setattr(cli, "_await_playing", lambda config, timeout=120.0: None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "сначала")

    assert cli.main(["моана", "2"]) == 0
    assert saved().pos == 0.0 and saved().audio == 1


def test_new_forgets_the_progress_and_goes_through_the_search(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--new` сбрасывает запись и проходит выбор заново (§4): вопроса «продолжить?» нет,
    а дальше начинается обычный путь с поиском (тут он упирается в ненастроенный Prowlarr).
    """
    remember(pos=2467.0, dur=5978.0)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")

    assert cli.main(["моана", "2", "--new"]) == 2

    assert State.load().get(KEY) is None
    assert "остановились" not in capsys.readouterr().out


def test_dry_resume_does_not_touch_the_unit(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    remember(pos=2467.0, dur=5978.0)
    monkeypatch.setattr("builtins.input", lambda prompt="": "")
    monkeypatch.setattr(
        cli, "start_play_unit", lambda key: pytest.fail("--dry юнитов не поднимает")
    )

    assert cli.main(["моана", "2", "--dry"]) == 0
    assert "каста нет" in capsys.readouterr().out


def test_status_is_honest_when_nothing_plays(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Юнита нет — «ничего не играет», но недосмотренное кино назвать не грех (§2.5)."""
    remember(pos=2467.0, dur=5978.0)
    monkeypatch.setattr(cli, "unit_active", lambda: False)

    assert cli.main(["status"]) == 0

    printed = capsys.readouterr().out
    assert printed.startswith("ничего не играет")
    assert "последнее: «Моана 2» на 0:41:07" in printed


def test_status_shows_what_is_playing_and_from_where(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Живой юнит: что играет, позиция/длительность, источник (§2.5)."""
    remember(pos=2467.0, dur=5978.0, audio=1, file_idx=2)
    monkeypatch.setattr(cli, "unit_active", lambda: True)

    assert cli.main(["status"]) == 0

    printed = capsys.readouterr().out
    assert "▶ «Моана 2» — 0:41:07 / 1:39:38" in printed
    assert KEY in printed and "файл #2" in printed and "дорожка 2" in printed


def test_status_names_the_unit_key_not_the_freshest_record(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Играющее определяется по ``--description`` юнита: рядом мог писать другой ход, и
    «самая свежая запись» назвала бы чужую картину (решение оркестратора, stage3 вопрос 3).
    """
    remember(pos=660.0, dur=5978.0)
    state = State.load()  # запись свежее, но она НЕ играет
    state.put("movie:чужое-кино:2020", Entry(title="Чужое кино", magnet="magnet:?xt=2", pos=10.0))
    state.save()
    monkeypatch.setattr(cli, "unit_active", lambda: True)
    monkeypatch.setattr(cli, "unit_key", lambda: KEY)

    assert cli.main(["status"]) == 0

    printed = capsys.readouterr().out
    assert "«Моана 2»" in printed and "Чужое кино" not in printed


def test_stop_reports_the_playing_record_and_asks_the_unit_before_killing_it(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """У мёртвого юнита описания уже не спросишь — ключ снимается до `systemctl stop`."""
    remember(pos=660.0, dur=5978.0)
    order: list[str] = []

    def ask_the_unit() -> str:
        order.append("key")
        return KEY

    monkeypatch.setattr(cli, "unit_active", lambda: True)
    monkeypatch.setattr(cli, "unit_key", ask_the_unit)
    monkeypatch.setattr(cli, "stop_play_unit", lambda: order.append("stop"))

    assert cli.main(["stop"]) == 0

    assert order == ["key", "stop"]
    assert "«Моана 2»" in capsys.readouterr().out


def test_stop_kills_the_unit_and_reports_the_fixed_position(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`cast stop`: юнит гасится, позицию в state дописывает сам юнит по SIGTERM (§2.5)."""
    remember(pos=660.0, dur=5978.0)
    stopped: list[bool] = []
    monkeypatch.setattr(cli, "unit_active", lambda: True)
    monkeypatch.setattr(cli, "stop_play_unit", lambda: stopped.append(True))

    assert cli.main(["stop"]) == 0

    assert stopped == [True]
    assert "остановлено: «Моана 2» на 0:11:00 / 1:39:38" in capsys.readouterr().out


def test_stop_without_playback_says_so(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "unit_active", lambda: False)
    monkeypatch.setattr(cli, "stop_play_unit", lambda: None)

    assert cli.main(["stop"]) == 0
    assert capsys.readouterr().out.strip() == "ничего не играет"


def test_systemd_plumbing_answers_about_a_unit_that_does_not_exist() -> None:
    """Разговор с systemd настоящий: несуществующий юнит — не «активен» и не исключение."""
    assert unit_active("torrcast-not-a-unit") is False
    assert isinstance(unit_why("torrcast-not-a-unit"), str)
