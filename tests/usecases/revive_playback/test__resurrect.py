"""Зеркало ступени подъёма: когда LOAD летит в приёмник, а когда показ гаснет честно."""

from __future__ import annotations

from pathlib import Path
from typing import cast

import pytest

from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import FakeReceiver, FakeSupply, feed_with_segments
from torrcast.domain.revive_settings import REVIVE_TRIES, SOURCE_TRIES
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._resurrect import _resurrect
from torrcast.usecases.revive_playback._revival_state import _RevivalState


def _ladder(supply: FakeSupply | None = None, **rest: float) -> _RevivalState:
    return _RevivalState(
        clock=FakeClock(now=1000.0),
        supply=cast(StreamSource, supply) if supply is not None else None,
        **rest,  # type: ignore[arg-type]
    )


def test_a_negative_place_is_an_ordinary_end_of_show(tmp_path: Path) -> None:
    """Поднимать неоткуда - это обычный конец показа, а не авария."""
    assert (
        _resurrect(
            _ladder(),
            cast(Receiver, FakeReceiver()),
            feed_with_segments(tmp_path),
            None,
            -1.0,
        )
        is False
    )


def test_a_finished_movie_is_not_resurrected(tmp_path: Path) -> None:
    """Фильм досмотрен: гаснущий экран тут и есть титры, поднимать его незачем."""
    feed = feed_with_segments(tmp_path)

    assert (
        _resurrect(_ladder(), cast(Receiver, FakeReceiver()), feed, None, feed.duration - 1.0)
        is False
    )


def test_the_zero_place_is_lawful_and_the_show_is_raised_from_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Начало картины - законное место: показ, не увидевший ни кадра, поднимают с нуля."""
    receiver = FakeReceiver(answer=0.0)
    ladder = _ladder(FakeSupply(), drop=0.0)

    held = _resurrect(ladder, cast(Receiver, receiver), feed_with_segments(tmp_path), None, 0.0)

    assert held is True
    assert receiver.replayed == [0.0], "лестница обязана попросить приёмник о нуле"
    assert ladder.tries == 1
    assert "показ поднят с" in capsys.readouterr().out


def test_the_spent_patience_ends_the_show_with_its_own_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Попытки кончились - показ гаснет и говорит, откуда его продолжит ``cast``."""
    ladder = _ladder()
    ladder.tries = REVIVE_TRIES

    held = _resurrect(
        ladder, cast(Receiver, FakeReceiver()), feed_with_segments(tmp_path), None, 120.0
    )

    assert (held, ladder.ended) == (False, True)
    assert "показ поднять не удалось" in capsys.readouterr().out


def test_a_receiver_that_dropped_the_show_is_waited_out_by_its_own_clock(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Виноват приёмник - ждут ЕГО, а не куски: до :attr:`drop` LOAD не летит вовсе."""
    receiver = FakeReceiver()
    ladder = _ladder(FakeSupply(), drop=30.0, pause=0.0)

    held = _resurrect(ladder, cast(Receiver, receiver), feed_with_segments(tmp_path), None, 120.0)

    assert held is True
    assert ladder.dropped is True, "источник спрошен и цел - виноват приёмник"
    assert receiver.replayed == [], "в темноте нулевой длины попытка сгорала бы впустую"
    assert "показ погас на" in capsys.readouterr().out


def test_a_darkness_from_the_clocks_zero_is_announced_once(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Темнота в нулевую секунду часов - одна строка, один круг вопросов, LOAD на 8-й.

    Сухой прогон считает часы от нуля, и нулевой ``since`` в такой темноте
    неотличим от «темноты нет»: приговор выносился заново на каждом тике, источник
    спрашивался двумя кругами, а первая попытка уезжала с 8-й секунды на 16-ю -
    сухой счёт лестницы врал ровно на круг вопросов. Признак темноты - причина
    (:attr:`_RevivalState.why`), а не часы.
    """
    clock = FakeClock()  # нулевые часы сухого прогона - не отладочная прихоть, а умолчание
    supply = FakeSupply()
    receiver = FakeReceiver()
    ladder = _RevivalState(clock=clock, supply=cast(StreamSource, supply), drop=4.0, pause=60.0)
    feed = feed_with_segments(tmp_path)
    feed.offline = ""  # упаковка не жаловалась: темноту устроил приёмник

    _resurrect(ladder, cast(Receiver, receiver), feed, None, 120.0)
    clock.sleep(2.0)  # шаг опроса показа
    _resurrect(ladder, cast(Receiver, receiver), feed, None, 120.0)

    printed = capsys.readouterr().out
    assert printed.count("показ погас на") == 1, "одна темнота - одна строка и один приговор"
    assert supply.asked == SOURCE_TRIES, "источник спрошен одним кругом, а не двумя"
    assert ladder.since == 0.0, "отсчёт темноты - от её начала, а не от второго тика"
    assert receiver.replayed == [120.0], "первая попытка - на 8-й секунде, а не на 16-й"
    assert ladder.tries == 1
