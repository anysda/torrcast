"""Повтор LOAD посреди показа: две попытки, своё место и запись в недельном следе."""

from __future__ import annotations

from typing import Any

import pytest

from tests.adapters.chromecast.cast.wired import Wired
from tests.fakes.journal import Tape
from torrcast.adapters.chromecast.cast.reload import _reload


class _Quiet(Wired):
    """Приёмник, у которого LOAD и перезапуск приложения только записываются."""

    def __init__(self, breaks: bool = False, **rest: Any) -> None:
        super().__init__(**rest)
        self.breaks = breaks
        self.loads: list[float] = []
        self.restarts = 0

    def _restart_app(self) -> None:
        self.restarts += 1
        if self.breaks:
            raise OSError("приёмник ушёл")

    def _load(self, at: float = 0.0, paused: bool = False) -> None:
        self.loads.append(at)


def test_the_receiver_is_brought_back_exactly_where_it_stumbled(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Манифест описывает весь фильм, поэтому вернуть приёмник туда - это позиция в LOAD.

    Приложение при этом поднимается чистым: залипший молчит на любой LOAD.
    """
    receiver = _Quiet()
    receiver._peak, receiver._error_code = 1272.4, 905

    assert _reload(receiver) is True
    assert receiver.loads == [1272.4]
    assert receiver.restarts == 1
    assert receiver._reloads == 1
    assert tape.events() == ["reload"]
    assert tape.named("reload")[0]["error"] == 905
    assert "retrying LOAD" in capsys.readouterr().out


def test_the_retries_run_out_and_the_trouble_stops_being_ours(
    tape: Tape,
) -> None:
    """Ровно столько попыток, сколько разрешает профиль: дальше это не наша авария."""
    receiver = _Quiet()
    receiver._reloads = receiver.profile.load_retries

    assert _reload(receiver) is False
    assert receiver.loads == []


def test_a_show_on_the_viewers_pause_is_not_started_over_by_a_retry(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Паузу ставил зритель, и смерть сессии её не отменяет: LOAD с автостартом не идёт.

    Живой замер 25-08-2026 на приставке: под голоданием упаковки она убила медиасессию
    сама через 29 с после паузы зрителя, и смерть пришла словом ``IDLE/ERROR``. Повтор
    LOAD перехватывал её раньше круга опроса и начинал фильм поверх паузы.
    """
    receiver = _Quiet()
    receiver._peak, receiver._paused = 1272.4, True

    assert _reload(receiver) is False
    assert receiver.loads == [], "показ, начатый поверх зрительской паузы, - брак"
    assert receiver.restarts == 0
    assert receiver._reloads == 0, "запас повторов остаётся настоящей смерти"
    assert tape.events() == []
    assert capsys.readouterr().out == ""


def test_a_receiver_that_left_mid_retry_is_left_to_the_next_tick(
    tape: Tape,
) -> None:
    """Приёмник мог просто уйти - решает следующий тик, а не исключение из сторожа."""
    receiver = _Quiet(breaks=True)
    receiver._peak = 100.0

    assert _reload(receiver) is False


def test_stepping_over_a_deadly_segment_moves_the_peak_with_the_show(
    tape: Tape, capsys: pytest.CaptureFixture[str]
) -> None:
    """Перешагнули - максимум обязан уехать вместе с показом.

    Иначе следующий нудж прицелится в оставленный позади кусок, а свой же прыжок мы
    примем за перемотку человека.
    """
    receiver = _Quiet()
    receiver.next_cut = lambda at: 137.095 if at < 137.095 else 152.0
    receiver._peak = 127.2
    receiver._deaths[137.095] = receiver.DEADLY_TRIES - 1

    assert _reload(receiver) is True

    (at,) = receiver.loads
    assert at > 127.2, "поднимаемся уже за убивающим куском"
    assert receiver._peak == at
    assert receiver._nudged_to == at
