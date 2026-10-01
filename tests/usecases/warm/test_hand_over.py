"""Зеркало стыка серий: идущий перекод старта следующей серии доляжет, остальное гаснет."""

from __future__ import annotations

import threading
import time
from pathlib import Path

from tests.usecases.warm.world import warmer, world
from torrcast.usecases.warm.hand_over import _hand_over
from torrcast.usecases.warm.warmer import Warmer


class _Watched(Warmer):
    """Прогрев, который помнит КАЖДЫЙ стоп: когда и лёг ли к тому мигу перекод старта."""

    __slots__ = ("stops",)
    stops: list[tuple[float, bool]]

    def stop(self) -> None:
        landing = self.landing
        self.stops.append((time.monotonic(), landing is not None and landing.is_set()))
        Warmer.stop(self)


def _pair(root: Path, landing: threading.Event | None) -> tuple[Warmer, _Watched]:
    world()
    show = warmer(root / "show")
    following = warmer(root / "next", kind=_Watched)
    assert isinstance(following, _Watched)
    following.landing = landing
    following.stops = []
    show.after = following
    return show, following


def test_the_recode_of_the_next_start_lands_before_the_next_episode_is_stopped(
    tmp_path: Path,
) -> None:
    landing = threading.Event()
    show, following = _pair(tmp_path, landing)
    began = time.monotonic()  # до таймера: перекод ляжет не раньше чем через 0.2 с от began
    threading.Timer(0.2, landing.set).start()

    _hand_over(show, 5.0)

    assert show.stopped, "прогрев досмотренной серии гаснет сразу"
    assert following.stopped, "остальная работа следующей серии гаснет, как при стопе"
    first_stop, landed = following.stops[0]
    assert landed, "перекод старта оборван до того, как лёг на диск"
    assert first_stop - began >= 0.2
    assert show.after is following, "цепочка остаётся той же, стык её не рвёт"


def test_a_hung_recode_is_put_out_after_the_deadline(tmp_path: Path) -> None:
    show, following = _pair(tmp_path, threading.Event())
    began = time.monotonic()

    _hand_over(show, 0.1)

    assert following.stopped, "ffmpeg перекода не остаётся без хозяина после срока"
    assert [landed for _at, landed in following.stops] == [False]
    assert time.monotonic() - began < 2.0, "стык ждёт не дольше срока"


def test_without_a_recode_in_flight_the_join_does_not_wait(tmp_path: Path) -> None:
    show, following = _pair(tmp_path, None)
    began = time.monotonic()

    _hand_over(show, 5.0)

    assert show.stopped and following.stopped
    assert time.monotonic() - began < 1.0, "ждать нечего - стык не задерживается"


def test_a_show_without_a_next_episode_just_stops(tmp_path: Path) -> None:
    world()
    show = warmer(tmp_path)

    _hand_over(show, 5.0)

    assert show.stopped and show.after is None
