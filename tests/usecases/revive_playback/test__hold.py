"""Зеркало держателя показа: круг опроса, конец сеанса и передача погасшего показа лестнице."""

from __future__ import annotations

import itertools
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest

from tests.fakes import composition
from tests.fakes.clock import FakeClock
from tests.usecases.feed_pack.world import FakeProc, packer, tract
from tests.usecases.revive_playback.world import (
    FakeReceiver,
    FakeSupply,
    PlainReceiver,
    feed_with_segments,
)
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.domain.position import Position
from torrcast.domain.revive_settings import SOURCE_TRIES
from torrcast.domain.start_settings import FIRST_FRAME_POLL
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.runtime.wire_feed import wire_feed
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.watch import Watch


@pytest.fixture(autouse=True)
def _silent_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Флажок картинки в зеркале никуда не пишется: меряем решение, а не файл."""
    composition.use_playing_mark(monkeypatch, lambda _path: None)


def test_a_show_that_cannot_be_raised_ends_by_itself(tmp_path: Path) -> None:
    """Приёмник погас, поднимать нечем - держатель возвращает ответ лестницы, а не висит."""
    receiver = PlainReceiver([(200.0, "PLAYING"), (0.0, "IDLE")])

    ended = _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        clock=FakeClock(now=1000.0),
    )

    assert ended is False, "лестница не поднимала - это обычный конец показа"


def test_one_black_screen_is_one_accident_for_the_viewer(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Повтор LOAD отвечает ``BUFFERING`` из ещё не ответившего приёмника, и экран чёрен.

    Считать такой ответ концом темноты значит рассказать зрителю об одном чёрном экране
    как о двух авариях и дважды расспросить ни в чём не виноватый источник.
    """
    supply = FakeSupply()
    receiver = FakeReceiver([(200.0, "PLAYING"), (0.0, "IDLE"), (200.0, "BUFFERING")], answer=-1.0)

    _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        supply=cast(StreamSource, supply),
        clock=FakeClock(now=1000.0),
    )

    printed = capsys.readouterr().out
    assert printed.count("показ погас на") == 1, "одна темнота - одна строка зрителю"
    assert supply.asked == SOURCE_TRIES, "источник спрошен одним кругом, а не двумя"


def test_a_long_pause_ends_the_show(tmp_path: Path) -> None:
    """Пауза длиной с вечер - показ окончен: юнит гасим, а не держим до утра."""
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(100.0, "PLAYING")] + [(100.0, "PAUSED")] * 4000)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps, "круг опроса обязан спать между вопросами приёмнику"


def test_the_receiver_is_asked_more_often_until_the_first_frame(tmp_path: Path) -> None:
    """До первого кадра приёмник спрашивается чаще: флажок «картинка» ставится на опросе.

    При шаге 2 с строка «старт NN с» запаздывала за настоящим кадром на 1.9-3.8 с.
    Первый же показанный кадр возвращает обычный шаг - учащение живёт ровно в окне
    старта, а не весь показ.
    """
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver(
        [(100.0, "PLAYING")] * 3 + [(101.0, "PLAYING")] + [(101.0, "PAUSED")] * 2000
    )

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps[:3] == [FIRST_FRAME_POLL] * 3, "указатель стоит - опрос учащён"
    assert set(clock.sleeps[3:]) == {2.0}, "кадр показан - окно старта кончилось"


def test_a_pause_before_the_first_frame_keeps_the_usual_poll(tmp_path: Path) -> None:
    """PLAYING без кадра, а следом пауза на пульте - окно старта закрыто: указатель не двигается.

    Пауза может длиться час, и учащённый опрос там жёг бы запросы к приёмнику впустую:
    кадру взяться неоткуда.
    """
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(50.0, "PLAYING")] + [(50.0, "PAUSED")] * 2000)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert ended is False
    assert clock.sleeps[0] == FIRST_FRAME_POLL, "PLAYING без кадра - окно старта открыто"
    assert set(clock.sleeps[1:]) == {2.0}, "на паузе опрос не учащается"


def test_a_dead_session_before_the_first_frame_keeps_the_usual_poll(tmp_path: Path) -> None:
    """Приёмник сказал PLAYING и умер, не показав кадра: темнота - не окно старта.

    В темноте показ ждёт возврата источника и лестницу подъёма, а указателю в мёртвой
    сессии взяться неоткуда - учащённый опрос там жёг бы приёмник впустую всю темноту.
    """
    clock = FakeClock(now=1000.0)
    receiver = FakeReceiver([(100.0, "PLAYING")] + [(0.0, "IDLE")] * 50)

    _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), clock=clock)

    assert clock.sleeps[0] == FIRST_FRAME_POLL, "PLAYING без кадра - окно старта открыто"
    assert clock.sleeps[1] == 2.0, "сессия мертва - окно старта закрыто"


def test_a_stuck_pointer_at_the_tail_finishes_the_session(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Указатель стоит у самого конца дольше минуты - сеанс доигран, и переход не теряется."""
    clock = FakeClock(now=1000.0)
    entry = Entry(title="Кино", magnet="magnet:?xt=1", dur=7200.0, pos=7190.0)
    watch = Watch(key="кино", entry=entry)
    receiver = FakeReceiver([(7190.0, "PLAYING")] * 200)

    ended = _hold(cast(Receiver, receiver), feed_with_segments(tmp_path), watch, clock=clock)

    assert ended is True
    assert "считаю доигранным" in capsys.readouterr().out


def test_a_dead_packing_with_a_healthy_source_falls_honestly(tmp_path: Path) -> None:
    """Упаковка сдалась, источник цел - показ падает честной ошибкой, а не молчанием."""
    feed = feed_with_segments(tmp_path)
    feed.fatal = "ffmpeg лёг"

    with pytest.raises(InfraError, match="упаковка оборвалась"):
        _hold(
            cast(Receiver, FakeReceiver()),
            feed,
            supply=cast(StreamSource, FakeSupply()),
            clock=FakeClock(now=1000.0),
        )


@pytest.fixture
def _feed_rewired() -> Iterator[None]:
    """Отдать ленте боевой медиатракт обратно: слоты - состояние процесса, не пробы."""
    yield
    wire_feed()


@pytest.mark.machine
def test_the_poll_circle_keeps_its_pace_while_a_torn_run_is_being_lifted(
    tmp_path: Path, _feed_rewired: None
) -> None:
    """🔴 Круг опроса слеп ровно столько, сколько часы показа стоят в чужой работе.

    Подъём оборванного прогона несёт в себе пробный прогон, до минуты по потолку
    (:data:`torrcast.domain.hls_wait.PILOT_TIMEOUT`), и упирается он в тот же нечитаемый
    источник, из-за которого прогон и оборвался. Пока часы показа ждали его сами,
    приёмника не спрашивали вовсе: слепы были ВСЕ метрики показа - место, подвис,
    перемотка, - а не только та упаковка, которую поднимали.

    Прогон рвётся посреди показа, а не до него: цена подъёма обязана попасть МЕЖДУ двумя
    вопросами приёмнику, иначе разрыв круга мерить не на чем. Часы тут ручные, а вот
    подъём и его цена настоящие: круг слепнет в реальном времени, а не в ручном.
    """
    lift_cost = 1.0

    def costly(_source: str, at: float, *_rest: object) -> tuple[float, float]:
        """Пробный прогон в нечитаемый источник: стоит времени и отвечает границей."""
        time.sleep(lift_cost)
        return at, at

    tract(clock=FakeClock(now=1000.0), settle_start=costly)
    show = feed_with_segments(tmp_path)
    alive = FakeProc()
    show.packer = packer(tmp_path, first=0, edge=2, out=show.out, proc=alive)
    asked: list[float] = []

    class _Watched(PlainReceiver):
        def position(self, front: float = 0.0) -> Position:
            asked.append(time.monotonic())
            if len(asked) == 2:
                alive.code = 1  # вход оборвался посреди показа
            return super().position(front)

    receiver = _Watched([(100.0, "PLAYING")] * 6 + [(0.0, "IDLE")])
    _hold(cast(Receiver, receiver), show, clock=FakeClock(now=1000.0))
    # Поток поднял продукт, а закрывает его тот, кто завёл эту пробу: замок свободен
    # ровно тогда, когда подъём договорил.
    assert show.lock.acquire(timeout=lift_cost * 10), "подъём прогона не кончился"
    show.lock.release()

    assert show.crashes == 1, "обрыв прогона не заметили - мерить нечего"
    assert len(asked) > 3, "круг опроса не сделал и трёх витков"
    blind = max(later - sooner for sooner, later in itertools.pairwise(asked))
    assert blind < lift_cost / 2, (
        f"круг опроса простоял {blind:.2f} с в чужой работе при её цене {lift_cost:.2f} с"
    )


@dataclass
class _ClosedReceiver:
    """Приёмник из сеанса 11-08-2026: показ убрали с экрана пультом.

    Слово о ходе показа при этом теряется вместе с сессией - вместо ``PAUSED`` или
    ``IDLE``/``ERROR`` приходит пустой статус с нулём, - а признак «экран пуст, и
    гасили его не мы» потерю сессии переживает и приходит в позиции.
    """

    script: list[tuple[float, str]]
    #: Места, с которых у приёмника просили поднять показ.
    replayed: list[float] = field(default_factory=list)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        pos, state = self.script.pop(0) if self.script else (0.0, "UNKNOWN")
        alive = state in {"PLAYING", "BUFFERING"}
        return Position(pos, 7200.0, alive, state, closed=not self.script and not alive)

    def replay(self, pos: float, paused: bool = False) -> float:
        self.replayed.append(pos)
        return pos


def test_the_show_closed_with_the_remote_is_not_raised_back(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Показ, закрытый рукой человека, обратно не поднимается ни разу.

    Сеанс 11-08-2026: приёмник ушёл в ``UNKNOWN``, приложение пропало с экрана целиком -
    и через 8 с показ поднялся сам, поперёк воли зрителя. Своя авария по-прежнему
    воскрешается: её от закрытия отличает то, что осталось на экране вместо показа.
    """
    receiver = _ClosedReceiver([(2231.0, "PLAYING"), (0.0, "UNKNOWN")])

    ended = _hold(
        cast(Receiver, receiver), feed_with_segments(tmp_path), clock=FakeClock(now=1000.0)
    )

    assert ended is True, "показ кончился по воле зрителя, а не аварией"
    assert receiver.replayed == [], "закрытый с пульта показ поднимать нельзя"
    assert "показ закрыт с пульта на 0:37:11" in capsys.readouterr().out


def test_a_show_closed_before_the_very_first_frame_is_not_raised_either(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Закрытие в первые секунды - то же самое: лестница воскрешения туда не идёт.

    Окно подъёма доходит до нулевой позиции (показ, умерший на 0:00, поднимается с
    начала картины), и без этой ветки закрытый до первого кадра показ включался бы
    обратно ровно так же, как закрытый посреди фильма.
    """
    receiver = _ClosedReceiver([(0.0, "UNKNOWN")])

    ended = _hold(
        cast(Receiver, receiver),
        feed_with_segments(tmp_path),
        clock=FakeClock(now=1000.0),
        start=2231.0,
        raised=False,
    )

    assert ended is True
    assert receiver.replayed == [], "показа не было ни кадра, но закрыл его зритель"
    assert "показ закрыт с пульта на 0:37:11" in capsys.readouterr().out
