"""Опрос места показа: максимум, перемотка пультом, отвал сессии и погасший показ."""

from __future__ import annotations

from typing import Any

from tests.adapters.chromecast.cast.wired import Status, Wired
from torrcast.adapters.chromecast.cast.position import _position


class _Scripted(Wired):
    """Приёмник, статус которого задан сценарием, а LOAD и подъём приложения - записи."""

    def __init__(self, status: Status, **rest: Any) -> None:
        super().__init__(**rest)
        self.reported = status
        self.loads: list[float] = []
        self.restarts = 0

    def _status(self) -> Any:
        return self.reported

    def _restart_app(self) -> None:
        self.restarts += 1

    def _load(self, at: float = 0.0) -> None:
        self.loads.append(at)


def test_real_progress_forgets_the_previous_nudges() -> None:
    """Показ поехал - прошлые прыжки сторожа больше не в счёт."""
    receiver = _Scripted(Status(pos=200.0))
    receiver._peak, receiver._stall_hits = 100.0, 3

    where = _position(receiver)

    assert where.pos == 200.0
    assert receiver._peak == 200.0
    assert receiver._stall_hits == 0


def test_the_peak_follows_a_human_who_rewound_with_the_remote() -> None:
    """Максимум обязан пойти за человеком, иначе нудж целится в покинутое им место.

    Замер на живом Q70D: откат с 31:31 на 10:00, через 35 с показ выкинуло обратно.
    """
    receiver = _Scripted(Status(pos=600.0))
    receiver._peak = 1891.0

    _position(receiver)

    assert receiver._peak == 600.0


def test_a_dead_session_zero_is_not_a_rewind_to_the_beginning() -> None:
    """У мёртвой сессии позиции нет вовсе, и её ноль - не «человек отмотал в начало».

    Замер на живом Q70D («Тачки 3»): показ споткнулся на 1:12:35, приёмник ушёл в
    ``IDLE/ERROR`` с нулём, ноль сошёл за перемотку - и повтор LOAD вернул человека к
    началу фильма.
    """
    receiver = _Scripted(Status(pos=0.0, state="IDLE", idle_reason="ERROR"))
    receiver._peak = 4355.0

    where = _position(receiver)

    assert receiver._peak == 4355.0
    assert where.pos == 4355.0, "повтор LOAD возвращает туда, где человек смотрел"
    assert receiver.loads == [4355.0], "повтор идёт в то же место, а не в ноль"


def test_a_live_receiver_zero_is_not_a_rewind_to_the_beginning_either() -> None:
    """Слово «я жив» ноль позицией не делает: своё место приёмник теряет и на ходу.

    Замер на живом Q70D («Отряд самоубийц»): картинка стояла на 34.3 с, приёмник отдал
    ноль, мёртвым себя не назвав, ноль сошёл за перемотку - и максимум уехал в начало
    фильма вместе с ним.
    """
    receiver = _Scripted(Status(pos=0.0, state="BUFFERING"))
    receiver._peak = 34.3

    _position(receiver)

    assert receiver._peak == 34.3


def test_a_human_who_rewound_to_the_very_beginning_is_followed_on_the_next_poll() -> None:
    """Отмотанный в начало показ ЕДЕТ, и ноль на нём держится один круг.

    Потерянное место стоит ровно нулём - этим они и различаются, а максимум обязан пойти
    за человеком, иначе следующий нудж вернёт его туда, откуда он только что ушёл.
    """
    receiver = _Scripted(Status(pos=0.0, state="PLAYING"))
    receiver._peak = 3660.0

    _position(receiver)
    assert receiver._peak == 3660.0, "первый круг ноль от потерянного места не отличает"

    receiver.reported = Status(pos=0.2, state="PLAYING")
    _position(receiver)
    assert receiver._peak == 0.2, "показ поехал - значит, это человек, и максимум идёт за ним"


def test_the_shown_frame_is_the_place_where_the_screen_was_alive() -> None:
    """Кадр на экране - это живое состояние и ненулевое место, и только оно."""
    receiver = _Scripted(Status(pos=34.3, state="PLAYING"))

    _position(receiver)
    assert receiver._shown == 34.3

    receiver.reported = Status(pos=0.0, state="BUFFERING")
    _position(receiver)
    assert receiver._shown == 34.3, "ноль в подгрузе показанным кадром не бывает"


def test_a_show_the_watchdog_gave_up_on_is_not_called_alive() -> None:
    """Сторож отработал и передаёт эстафету воскрешению: живым такой показ звать нельзя.

    Состояние отдаётся как есть - врать о нём незачем, а решает зовущий по ``playing``.
    """
    receiver = _Scripted(Status(pos=100.0, state="BUFFERING"))
    receiver._gone = True

    where = _position(receiver)

    assert where.playing is False
    assert where.state == "BUFFERING"


def test_a_frame_on_the_screen_resets_the_ladder_of_blind_jumps() -> None:
    """Кадр - единственное доказательство того, что нудж вылечил застрявший кусок."""
    receiver = _Scripted(Status(pos=100.0, state="PLAYING"))
    receiver._blind, receiver._gone = 3, True

    _position(receiver)

    assert receiver._blind == 0
    assert receiver._gone is False


def test_a_show_that_is_not_buffering_clears_the_stall_clock() -> None:
    """Показ пошёл - отсчёт зависания начинается заново, а не продолжается со старого."""
    receiver = _Scripted(Status(pos=100.0, state="PLAYING"))
    receiver._stall_at, receiver._stall_since = 100.0, 5.0

    _position(receiver)

    assert receiver._stall_at == -1.0
    assert receiver._stall_since == 0.0
