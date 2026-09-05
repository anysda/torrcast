"""Зеркало :mod:`torrcast.usecases.worker`: показ внутри юнита и уборка его раздачи."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from tests.fakes import composition
from torrcast.adapters.filesystem.state.state import State
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.choice import Choice
from torrcast.domain.entry import Entry
from torrcast.domain.media import Media
from torrcast.domain.profile import ANDROID_TV, CAUTIOUS
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.worker import _cmd_worker

KEY = "movie:брат:1997"


class _FakeTorrServer:
    """Служба раздач в объёме, который нужен юнику показа: поднять, отдать, убрать."""

    def __init__(self, url: str, timeout: float = 30.0) -> None:
        self.url = url

    def add(self, magnet: str) -> str:
        _added.append(magnet)
        return "hash"

    def drop(self, torrent_hash: str) -> bool:
        _dropped.append(torrent_hash)
        return True

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        return [TorrFile(0, "Brat.mkv", 1024**3)]

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"


_added: list[str] = []
_dropped: list[str] = []


@pytest.fixture(autouse=True)
def _own_show(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setenv("TORRCAST_CONFIG", str(tmp_path / "config.json"))
    _added.clear()
    _dropped.clear()
    state = State()
    state.put(KEY, Entry(title="Брат", magnet="magnet:?xt=1", kind="movie", dur=90.0))
    state.save()
    composition.use_engines(monkeypatch, _FakeTorrServer)
    composition.use_prober(
        monkeypatch, lambda url, timeout=90.0, alive=None: Media(90.0, (), "h264")
    )
    composition.use_receivers(monkeypatch, lambda kind, address, cert, profile=None: object())


def _played(
    config: Any, source: str, audio: int, about: str, clock: Any, watch: Any, **_rest: Any
) -> int:
    """Показ одним махом: сеанс досмотрен до конца, и очередь на этом кончается."""
    watch.see(watch.entry.dur)
    watch.close()
    return 0


def test_the_unit_asks_the_receiver_about_itself_and_says_the_answer_aloud(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Юнит переживает смену серии и профиль выбирает сам, а не получает от команды.

    Решение это меняет пороги отбора и перекода, поэтому оно печатается: молча
    подменённый профиль объяснил бы и лишний перекод, и отказ, и понять их было бы нечем.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(ANDROID_TV, "спрошен приёмник"))

    assert _cmd_worker(KEY, play=_played) == 0

    said = phrase("worker.receiver_profile", title=ANDROID_TV.title, how="спрошен приёмник")
    assert said in capsys.readouterr().out


def test_the_profile_the_unit_chose_is_the_one_it_names(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Отрицательная проба к строке выше: другой ответ приёмника - другая строка."""
    composition.use_profile(monkeypatch, lambda config: Choice(CAUTIOUS, "ответа нет"))

    assert _cmd_worker(KEY, play=_played) == 0

    said = phrase("worker.receiver_profile", title=CAUTIOUS.title, how="ответа нет")
    assert said in capsys.readouterr().out


def test_the_unit_takes_its_own_torrent_away_when_the_show_ends(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Хозяин раздачи один - юнит; не убери он её, они копились бы до перезапуска службы.

    Уборка раздачи не единственный след досмотра: сторож ещё и говорит вслух, что
    досмотрено и до какого места, - молчание тут ничем не отличалось бы от повисшего
    сеанса, который просто не убрал за собой раздачу.
    """
    composition.use_profile(monkeypatch, lambda config: Choice(ANDROID_TV, "спрошен приёмник"))

    assert _cmd_worker(KEY, play=_played) == 0

    assert _added == ["magnet:?xt=1"]
    assert _dropped == ["hash"]
    said = phrase("watch.finished", what="", pos=_hms(90.0), duration=_hms(90.0))
    assert said in capsys.readouterr().out, "досмотрено объявлено вслух, а не только в state"
