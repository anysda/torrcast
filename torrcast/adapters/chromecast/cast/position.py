"""Опрос места показа: он же и весь сторож - подвис, перемотка, отвал и темнота.

Зовёт его показ раз в две секунды, и это единственный вход в сторожа."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.chromecast.cast.nudge import _nudge
from torrcast.adapters.chromecast.cast.reload import _reload
from torrcast.adapters.chromecast.cast.say_skip import _say_skip
from torrcast.adapters.chromecast.cast.watch_seek import _watch_seek
from torrcast.domain.position import Position

if TYPE_CHECKING:
    from torrcast.adapters.chromecast.cast.receiver_talk import _Talk


def _position(rcv: _Talk, front: float = 0.0) -> Position:
    """Где показ и жив ли он; попутно - вся работа сторожа за этот опрос."""
    st = rcv._status()
    state = str(st.player_state or "")
    pos = st.current_time or 0.0
    if pos > rcv._peak:  # реальный прогресс - прошлые нуджи больше не в счёт
        rcv._peak, rcv._stall_hits = pos, 0
    elif state != "IDLE" and rcv._peak - pos > rcv.REWIND:
        # Позиция уехала назад глубже допуска - это перемотка пультом: сами мы
        # прыгаем только вперёд. Максимум обязан пойти за человеком, иначе нудж
        # целится в место, которое он только что покинул. Замер на живом Q70D:
        # откат с 31:31 на 10:00, через 35 с показ выкинуло обратно на
        # 31:31 (и второй раз - с 29:55 на 30:59 нуджем через накопленные попытки).
        #
        # 🔴 ``IDLE`` из этого правила исключён: у мёртвой сессии позиции нет вовсе,
        # и ``current_time`` в ней - не «человек отмотал в начало», а «отвечать
        # некому». Замер на живом Q70D (обрыв связи, «Тачки 3»): показ споткнулся на
        # 1:12:35, приёмник ушёл в ``IDLE/ERROR`` с нулём, ноль сошёл за перемотку - и
        # повтор LOAD вернул человека не туда, где он смотрел, а к началу фильма.
        rcv._peak, rcv._stall_hits = pos, 0
    if state == "PLAYING":
        # Кадр на экране - лестница нуджей начинается с нуля, чем бы она ни кончилась.
        rcv._blind, rcv._gone = 0, False
        _say_skip(rcv, pos)
    _watch_seek(rcv, pos, state)
    if state == "BUFFERING":
        _nudge(rcv, pos, front)
    else:
        rcv._stall_at, rcv._stall_since = -1.0, 0.0
    if state == "IDLE" and st.idle_reason == "ERROR" and _reload(rcv):
        return Position(rcv._peak, st.duration or 0.0, True, "BUFFERING")
    if rcv._gone:
        # 🔴 Сторож своё отработал и передаёт эстафету воскрешению: живым такой показ
        # называть больше нельзя, хотя приёмник и рапортует BUFFERING. Состояние
        # отдаём как есть - врать о нём незачем, а решает зовущий по ``playing``.
        return Position(pos, st.duration or 0.0, False, state)
    return Position(pos, st.duration or 0.0, st.player_is_playing, state)
