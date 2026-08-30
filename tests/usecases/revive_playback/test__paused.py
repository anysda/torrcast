"""Зеркало паузы зрителя: она переживает потерю сессии приёмником."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import feed_with_segments
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.position import Position
from torrcast.domain.start_settings import PAUSE_LIMIT, PAUSE_SECONDS
from torrcast.ports.receiver import Receiver
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.revive_playback._hold import _hold


@dataclass
class _LosingReceiver:
    """Приёмник из живого сеанса 24-08-2026: под чужой паузой роняет медиасессию.

    Зритель поставил показ на паузу, упаковка по сроку погашена нами же, и девятнадцать
    минут спустя приёмник забывает сессию: вместо ``PAUSED`` с местом - ``UNKNOWN`` с
    нулём. С этого момента его слово перестаёт различать паузу зрителя и смерть показа.

    На LOAD без автостарта (``paused=True``) приёмник отвечает возвратом сессии на
    закладку - и стоит на ней, пока зритель не нажмёт play. На обычный LOAD отвечает
    тем, о чём просят: показом с того же места. Отказ заготовлен тоже
    (:attr:`answer`): второй темноте прогона кончаться.
    """

    script: list[tuple[float, str]]
    #: Подъёмы, которые у приёмника просили: (место, на паузу ли).
    replays: list[tuple[float, bool]] = field(default_factory=list)
    #: Слова, которые приёмник отвечал после потери сессии.
    after_loss: list[str] = field(default_factory=list)
    #: Позиции, которые приёмник играл.
    played: list[float] = field(default_factory=list)
    #: Куда вернули сессию на паузу; ``-1`` - не возвращали.
    restored: float = -1.0
    #: С какого места приёмник играет; ``-1`` - не играет.
    playing: float = -1.0
    #: Чем обычный подъём отвечает: местом или отказом отрицательным числом.
    answer: float = 0.0
    #: Через сколько опросов на паузе зритель вернётся и нажмёт play; 0 - не вернётся.
    viewer_back: int = 0
    lost: bool = False
    plays: int = 0

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        if self.playing >= 0:
            pos, state = self.playing, "PLAYING"
            self.played.append(pos)
            self.playing += 2.0
            self.plays += 1
            if self.plays >= 5:
                self.playing, self.plays = -1.0, 0  # приёмник бросил показ снова
        elif self.restored >= 0:
            pos, state = self.restored, "PAUSED"
            if self.viewer_back:
                self.viewer_back -= 1
                if not self.viewer_back:  # зритель вернулся и нажал play
                    self.playing, self.restored = self.restored, -1.0
        else:
            pos, state = self.script.pop(0) if self.script else (0.0, "UNKNOWN")
        if state == "UNKNOWN":
            self.lost = True
        if self.lost:
            self.after_loss.append(state)
        return Position(pos, 7200.0, state in {"PLAYING", "BUFFERING"}, state)

    def replay(self, pos: float, paused: bool = False) -> float:
        self.replays.append((pos, paused))
        if paused:
            self.restored = pos
            return pos
        if self.answer < 0:
            return self.answer
        self.playing = pos
        return pos


def test_the_viewers_pause_survives_the_lost_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Пауза зрителя переживает потерю сессии: показ сам не начинается никогда.

    Живой сеанс 24-08-2026, Samsung Q70D: пауза на 0:37:11, через минуту упаковка
    погашена, ещё через девятнадцать приёмник забыл сессию - и показ честно поднял
    фильм с закладки в ``PLAYING``. Никто не просил: снять паузу зрителя может только
    зритель. Сессию возвращают на закладку БЕЗ начала показа, а срок паузы тикает
    без сессии и по-прежнему кончает сеанс.
    """
    clock = FakeClock(now=1000.0)
    held = int(PAUSE_SECONDS / 2.0) + 2  # опрос раз в 2 с - пауза пережила срок упаковки
    receiver = _LosingReceiver([(2231.0, "PLAYING"), *[(2231.0, "PAUSED")] * held])

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False, "показ кончился сроком паузы, а не снятием её"
    assert receiver.replays and all(paused for _, paused in receiver.replays), (
        "сессию возвращают на закладку БЕЗ начала показа"
    )
    assert {pos for pos, _ in receiver.replays} == {2231.0}, "подъём ровно на закладку зрителя"
    assert "PLAYING" not in receiver.after_loss, "показ сам не начинается"
    assert clock.now - 1000.0 >= PAUSE_LIMIT, "срок паузы тикал и без сессии"
    out = capsys.readouterr().out
    assert phrase("revive.pause_from_remote") in out
    assert phrase("revive.pause_session_lost", pos=_hms(2231.0)) in out


def test_the_restored_pause_starts_on_the_viewers_word(tmp_path: Path) -> None:
    """Зритель вернулся и нажал play: показ пошёл с закладки, не раньше и не с начала.

    Смерть ПОСЛЕ слова зрителя - уже настоящая смерть: её поднимает обычная лестница,
    и сужать её эта правка не вправе. Второй темноте приёмник тут отвечает отказом,
    чтобы прогон кончился: меряется место, С КОТОРОГО показ пошёл, а не её судьба.
    """
    clock = FakeClock(now=1000.0)
    held = int(PAUSE_SECONDS / 2.0) + 2
    receiver = _LosingReceiver(
        [(2231.0, "PAUSED")] * held,
        viewer_back=5,
        answer=-1.0,  # вторую темноту приёмник не поднимает - прогону пора кончиться
    )

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is True
    assert receiver.played[:3] == [2231.0, 2233.0, 2235.0], "слово зрителя - с закладки"
